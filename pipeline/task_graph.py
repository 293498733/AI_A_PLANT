"""任务图执行器 — 依赖拓扑排序 + 逐任务 fresh session 执行（沙箱隔离）。

v3.3: 并发上限控制 — ThreadPoolExecutor + parallel_group 分组 + max_workers 背压。
v3.4: 单任务验证闭环 — goose 产出后沙箱内编译+测试，全部通过才 sync。
v3.8: 按任务类型验证 + 三元任务状态 + JAVA_HOME 加固 + 阶段前置守卫。
"""

import json
import os
import re
import time
import logging
import subprocess
import threading
from pathlib import Path
from itertools import groupby
from concurrent.futures import ThreadPoolExecutor, as_completed

from pipeline.config import TaskConfig, load_task_graph, load_profile
from pipeline.task_state import (
    TaskStateManager, STATUS_PENDING, STATUS_COMPLETED,
    STATUS_CODE_PRODUCED, STATUS_FAILED_NO_OUTPUT,
    STATUS_FAILED, STATUS_SKIPPED,
)
from pipeline.task_context import ContextAssembler
from pipeline.snapshot import SnapshotManager
from pipeline.knowledge_accumulator import KnowledgeAccumulator
from pipeline.git_ops import GitOps
from pipeline.executor import run_task, detect_jdk, JdkNotFound
from pipeline.error_handler import handle_task_error, TaskAction
from pipeline.sandbox import SandboxManager, SandboxCreateError

logger = logging.getLogger("ai-dev-flow")

SEPARATOR = "=" * 60

# _execute_single_task 返回值
_TASK_OK = "ok"
_TASK_RETRY = "retry"
_TASK_SKIP = "skip"
_TASK_ABORT = "abort"
_TASK_NOTE_EXIT = "note_exit"


def execute_task_graph(
    project_root: Path,
    ai_dev_dir: Path,
    tasks_file: Path,
    profile_path: Path,
    task_recipe: str = "recipes/steps/task-template.yaml",
    quiet: bool = True,
) -> tuple[bool, dict]:
    """执行任务图。

    quiet=True 时 goose 子进程传 -q，隐藏文件扫描噪音，仅显示模型回复。

    Returns:
        (success, results_dict) — success=True 表示所有任务完成或跳过
    """
    graph = load_task_graph(tasks_file)
    tasks: dict[str, TaskConfig] = {t.id: t for t in graph.tasks}
    task_ids = list(tasks.keys())

    # 检测循环依赖
    cycle = _detect_cycle(tasks)
    if cycle:
        logger.error(f"Circular dependency detected: {' -> '.join(cycle)}")
        return False, {}

    # 检查 task_state.json 是否有上次运行残留的不一致条目
    from pipeline.state import read_task_state as _read_ts
    _existing = _read_ts(ai_dev_dir) or {}
    _stale = [tid for tid in _existing if tid not in task_ids]
    if _stale:
        logger.warning(
            f"task_state.json has {len(_stale)} stale entries from a previous run "
            f"(tasks.yaml was likely overwritten). Clearing: {_stale}"
        )
        for tid in _stale:
            del _existing[tid]
        from pipeline.state import write_task_state as _write_ts
        _write_ts(ai_dev_dir, _existing)

    # 初始化状态管理器
    dependencies = {tid: t.depends_on for tid, t in tasks.items()}
    modules = {tid: t.module for tid, t in tasks.items() if t.module}
    state_mgr = TaskStateManager(ai_dev_dir, task_ids, dependencies, modules)
    state_mgr.reset_in_progress()  # 崩溃恢复

    # 清理上次崩溃可能留下的残留 sandbox
    SandboxManager.cleanup_orphaned(project_root, ai_dev_dir)

    # 自动跳过已耗尽重试的失败任务（包括 code_produced 和 failed_no_output）
    for tid in task_ids:
        tr = state_mgr.tasks[tid]
        if tr["status"] in (STATUS_FAILED, STATUS_FAILED_NO_OUTPUT) and tr["retries"] >= tasks[tid].retry_limit:
            logger.warning(f"Task {tid} retries exhausted ({tr['retries']}/{tasks[tid].retry_limit}), auto-skip")
            state_mgr.tasks[tid]["status"] = STATUS_SKIPPED
            state_mgr.tasks[tid]["notes"] = "Auto-skipped: retries exhausted"
    state_mgr.save()

    snapshot_mgr = SnapshotManager(ai_dev_dir, project_root)
    knowledge_mgr = KnowledgeAccumulator(ai_dev_dir)
    context_asm = ContextAssembler(project_root, ai_dev_dir, snapshot_mgr)
    try:
        git = GitOps(project_root)
        git_available = True
    except RuntimeError:
        logger.warning("Not a git repository — auto-commit disabled")
        git = None
        git_available = False

    print()
    print(SEPARATOR)
    print(f"  任务图执行 — {len(graph.tasks)} 个任务")
    print(f"  预估总 turns: {graph.total_estimated_turns}")
    max_workers = graph.max_workers
    if max_workers > 1:
        print(f"  并发上限: {max_workers} workers")
    print(SEPARATOR)

    lock = threading.Lock()
    total = len(graph.tasks)
    task_recipe_path = str(Path(__file__).resolve().parent.parent / task_recipe)

    # 加载 profile（供各任务按类型解析验证步骤）
    profile = load_profile(profile_path) or {}

    # JDK 自动检测（所有需要 Java 验证的任务共享）
    verify_env: dict[str, str] = {}
    try:
        jdk_required = int(profile.get("backend", {}).get("jdk", {}).get("compileRelease", 17))
    except (TypeError, ValueError):
        jdk_required = 17
    try:
        jdk_home = detect_jdk(jdk_required)
        verify_env["JAVA_HOME"] = jdk_home
        print(f"  JDK 检测: {jdk_home}")
        print(f"  验证策略: 按任务类型自动选择（auto → backend/frontend/none）")
    except JdkNotFound as e:
        logger.warning(f"JDK detection failed: {e}")
        print(f"  ⚠️ {e}")
    print(SEPARATOR)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        while True:
            # 计算已完成集合（code_produced 视为完成，下游不应被阻塞）
            completed_ids: set[str] = set()
            for tid, tr in state_mgr.tasks.items():
                if tr["status"] in (STATUS_COMPLETED, STATUS_SKIPPED, STATUS_CODE_PRODUCED):
                    completed_ids.add(tid)

            # 找就绪任务
            ready = state_mgr.get_next_ready(completed_ids)

            # 检查是否全部完成
            if not ready:
                done, _, failed = state_mgr.progress()
                if done >= total:
                    print()
                    print(SEPARATOR)
                    print(f"  任务图完成 — {done}/{total} 任务")
                    print(SEPARATOR)
                    return True, state_mgr.tasks
                elif failed > 0 and all(
                    state_mgr.tasks[tid]["status"] in (STATUS_FAILED, STATUS_FAILED_NO_OUTPUT)
                    for tid in task_ids
                    if state_mgr.tasks[tid]["status"] not in (STATUS_COMPLETED, STATUS_SKIPPED, STATUS_CODE_PRODUCED)
                ):
                    logger.error("Task graph blocked by failures")
                    return False, state_mgr.tasks
                else:
                    # Deadlock check
                    pending = [tid for tid in task_ids
                               if state_mgr.tasks[tid]["status"] == STATUS_PENDING
                               and tid not in ready]
                    blocked = []
                    for tid in pending:
                        task = tasks[tid]
                        unmet = [dep for dep in task.depends_on if dep not in completed_ids]
                        if any(state_mgr.tasks[dep]["status"] in (STATUS_FAILED, STATUS_FAILED_NO_OUTPUT) for dep in unmet):
                            blocked.append(tid)
                    if blocked:
                        logger.error(f"Tasks blocked by failed dependencies: {blocked}")
                    return False, state_mgr.tasks

            # 排序：P0 优先，estimated_turns 小的优先
            def _sort_key(tid):
                t = tasks[tid]
                p = 0 if t.priority == "P0" else (1 if t.priority == "P1" else 2)
                return (p, t.estimated_turns)
            ready.sort(key=_sort_key)

            # 按 parallel_group 分组（None = 各自独立组）
            groups = [list(g) for _, g in groupby(ready, key=lambda tid: tasks[tid].parallel_group)]

            # 取第一个组执行，完成后重新计算 ready（新任务可能被解锁）
            group = groups[0]

            # 打印组内所有任务头
            for i, tid in enumerate(group):
                task = tasks[tid]
                tr = state_mgr.tasks[tid]
                seq = len(completed_ids) + i + 1
                print()
                print(SEPARATOR)
                print(f"  [{seq}/{total}] {task.name} ({task.id})")
                print(f"  分类: {task.category} | 优先级: {task.priority} | 预估: {task.estimated_turns}turns")
                if task.module:
                    mod_prog = state_mgr.get_module_progress()
                    if task.module in mod_prog:
                        d, t, f = mod_prog[task.module]
                        bar = _module_bar(d - (1 if f == 0 else 0), t)
                        print(f"  模块: {task.module} {bar}")
                print(SEPARATOR)

            # 提交组内所有任务到线程池
            futures = {}
            for tid in group:
                future = executor.submit(
                    _execute_single_task,
                    tid=tid,
                    task=tasks[tid],
                    state_mgr=state_mgr,
                    context_asm=context_asm,
                    knowledge_mgr=knowledge_mgr,
                    snapshot_mgr=snapshot_mgr,
                    git=git,
                    git_available=git_available,
                    project_root=project_root,
                    ai_dev_dir=ai_dev_dir,
                    profile_path=profile_path,
                    task_recipe=task_recipe_path,
                    lock=lock,
                    profile=profile,
                    verify_env=verify_env,
                    quiet=quiet,
                )
                futures[future] = tid

            # 等待组内所有任务完成
            retry_needed = False
            abort = False
            for future in as_completed(futures):
                tid = futures[future]
                try:
                    result = future.result()
                except Exception as e:
                    logger.error(f"Task {tid} thread exception: {e}")
                    with lock:
                        state_mgr.mark_failed(tid, str(e))
                        state_mgr.save()
                    result = _TASK_RETRY

                if result == _TASK_RETRY:
                    retry_needed = True
                elif result in (_TASK_ABORT, _TASK_NOTE_EXIT):
                    abort = True

            if abort:
                return False, state_mgr.tasks
            if retry_needed:
                continue

    return True, state_mgr.tasks


def _execute_single_task(
    *,
    tid: str,
    task: TaskConfig,
    state_mgr: TaskStateManager,
    context_asm: ContextAssembler,
    knowledge_mgr: KnowledgeAccumulator,
    snapshot_mgr: SnapshotManager,
    git,
    git_available: bool,
    project_root: Path,
    ai_dev_dir: Path,
    profile_path: Path,
    task_recipe: str,
    lock: threading.Lock,
    profile: dict | None = None,
    verify_env: dict[str, str] | None = None,
    quiet: bool = True,
) -> str:
    """执行单个原子任务（在 worker 线程中运行）。

    锁范围：pre-execution（状态写入 + 沙箱创建）和 post-execution（状态更新 + git + snapshot）
    不锁定：goose 子进程执行 + 验证步骤（主要耗时部分）。

    profile: 项目画像，用于 _resolve_verification_steps 按任务类型选择验证策略。
    verify_env: 注入到验证子进程的环境变量（如 JAVA_HOME）。
    quiet: True 时 goose 传 -q，隐藏文件扫描噪音。
    """

    # === Pre-execution (under lock) ===
    with lock:
        # Git pre-check (on real project)
        if git_available and git:
            git.pre_task_check()

        # 上下文组装（含历史决策注入）
        ctx = context_asm.assemble(task)
        relevant_knowledge = knowledge_mgr.query(task.category)
        if relevant_knowledge:
            ctx.context_notes += "\n\n### Relevant Past Decisions\n" + "\n---\n".join(relevant_knowledge)
        context_text = context_asm.render_prompt(task, ctx)

        state_mgr.mark_in_progress(tid)
        state_mgr.save()

        # 创建沙箱（可选择跳过）
        sandbox = None
        sandbox_path = project_root
        if task.sandbox_enabled:
            sandbox = SandboxManager(project_root, ai_dev_dir)
            try:
                sandbox_path = sandbox.create(task.id)
            except SandboxCreateError as e:
                logger.error(f"Sandbox create failed for {tid}: {e}")
                logger.warning(f"Falling back to non-sandboxed execution for {tid}")
                sandbox_path = project_root
                sandbox = None

    # === Execution (no lock — goose subprocess runs independently) ===
    task_start = time.time()

    base_params = {
        "task_name": task.name,
        "task_description": task.description,
        "project_root": str(sandbox_path),
        "profile": str(profile_path),
        "context_file": _write_context_file(ai_dev_dir, tid, context_text),
    }

    def _on_task_timeout():
        logger.error(f"Task {tid}: watchdog timeout, sandbox preserved at {sandbox_path}")

    if task.sub_pipeline:
        # 子管线：方案 → 编码 → 测试 → 审查
        result, run_exception = _run_sub_pipeline(
            tid=tid,
            task=task,
            base_params=base_params,
            sandbox_path=sandbox_path,
            ai_dev_dir=ai_dev_dir,
            context_text=context_text,
            task_recipe=task_recipe,
            quiet=quiet,
            on_timeout=_on_task_timeout,
            env=verify_env or None,
        )
        elapsed = int(time.time() - task_start)
        mins, secs = divmod(elapsed, 60)
    else:
        try:
            result = run_task(
                recipe=task_recipe,
                max_turns=task.estimated_turns,
                params=base_params,
                cwd=sandbox_path,
                timeout_minutes=task.timeout_minutes,
                on_timeout=_on_task_timeout,
                quiet=quiet,
                env=verify_env or None,
            )
        except Exception as e:
            logger.error(f"Task {tid}: run_task exception: {e}")
            result = None
            run_exception = e
        else:
            run_exception = None
        elapsed = int(time.time() - task_start)
        mins, secs = divmod(elapsed, 60)

    # === Post-execution (under lock) ===
    with lock:
        if run_exception is not None:
            logger.error(f"Task {tid} exception: {run_exception}")
            if sandbox:
                logger.warning(f"Task {tid} exception, sandbox preserved at: {sandbox_path}")
            state_mgr.mark_failed(tid, str(run_exception))
            state_mgr.save()
            tr = state_mgr.tasks[tid]
            action = handle_task_error(
                tid, task.name, tr["retries"],
                task.retry_limit, ai_dev_dir
            )
            if action == TaskAction.RETRY_TASK:
                state_mgr.tasks[tid]["status"] = STATUS_PENDING
                state_mgr.save()
                return _TASK_RETRY
            elif action == TaskAction.ABORT_GRAPH:
                return _TASK_ABORT
            elif action == TaskAction.NOTE_EXIT:
                return _TASK_NOTE_EXIT
            return _TASK_SKIP

        if result.returncode == 0:
            # 验证沙箱中的产出文件
            missing = [f for f in task.output_files
                       if not (sandbox_path / f).exists()]
            if missing:
                logger.warning(f"Task {tid} completed but missing in sandbox: {missing}")
                if sandbox:
                    logger.warning(f"Sandbox preserved at: {sandbox_path}")
                err = _build_structured_error(
                    "output_check", result.returncode,
                    f"Goose completed but missing output files: {missing}",
                    task, sandbox_path, verify_env,
                )
                state_mgr.mark_failed_no_output(tid, err)
                state_mgr.save()
                print(f"  ❌ 失败 ({mins}m{secs}s) — 缺少文件: {missing}")
                tr = state_mgr.tasks[tid]
                action = handle_task_error(
                    tid, task.name, tr["retries"],
                    task.retry_limit, ai_dev_dir
                )
                if action == TaskAction.RETRY_TASK:
                    state_mgr.tasks[tid]["status"] = STATUS_PENDING
                    state_mgr.tasks[tid]["started_at"] = None
                    state_mgr.save()
                    return _TASK_RETRY
                elif action == TaskAction.ABORT_GRAPH:
                    return _TASK_ABORT
                elif action == TaskAction.NOTE_EXIT:
                    return _TASK_NOTE_EXIT
                return _TASK_SKIP
            else:
                # 检测非预期修改
                if sandbox:
                    extra = sandbox.detect_extra_modifications(
                        set(task.output_files)
                    )
                    if extra:
                        logger.warning(f"Task {tid} modified undeclared files: {extra}")

                # === 验证闭环：按任务类型选择验证策略（v3.8） ===
                verify_failed = False
                task_verification = _resolve_verification_steps(task, profile)
                if task_verification:
                    labels = [label for label, _ in task_verification]
                    print(f"  🔍 验证中 ({task.verification}: {' → '.join(labels)})...")
                    for label, commands in task_verification:
                        passed, output = _run_verification_step(sandbox_path, label, commands, env=verify_env)
                        if not passed:
                            print(f"  ❌ 验证失败: {label}")
                            for line in output.splitlines()[-15:]:
                                print(f"      {line}")
                            verify_failed = True
                            break
                        else:
                            print(f"  ✅ {label} 通过")
                    if verify_failed:
                        # 保留沙箱供排查
                        if sandbox:
                            logger.warning(f"Task {tid} verification failed, sandbox preserved at: {sandbox_path}")
                        err = _build_structured_error(
                            "verification", result.returncode,
                            f"Verification failed: {label}\n{output[-500:]}",
                            task, sandbox_path, verify_env,
                            commands=[cmd for _, cmds in task_verification for cmd in cmds],
                        )
                        state_mgr.mark_code_produced(tid, task.output_files, verification_error=err)
                        state_mgr.save()
                        print(f"  ⚠️ 代码已产出，验证未通过 ({mins}m{secs}s)")
                        tr = state_mgr.tasks[tid]
                        action = handle_task_error(
                            tid, task.name, tr["retries"],
                            task.retry_limit, ai_dev_dir
                        )
                        if action == TaskAction.RETRY_TASK:
                            state_mgr.tasks[tid]["status"] = STATUS_PENDING
                            state_mgr.tasks[tid]["started_at"] = None
                            state_mgr.save()
                            return _TASK_RETRY
                        elif action == TaskAction.ABORT_GRAPH:
                            return _TASK_ABORT
                        elif action == TaskAction.NOTE_EXIT:
                            return _TASK_NOTE_EXIT
                        return _TASK_SKIP

                # 从沙箱同步产出文件到真实项目
                if sandbox:
                    synced = sandbox.sync_outputs(task.output_files)
                    logger.info(f"Synced {len(synced)} files from sandbox")
                    sandbox.destroy()

                # 在真实项目上 git commit
                commit_hash = ""
                if git_available and git:
                    commit_hash = git.commit_task(
                        tid, task.name, task.category,
                        task.priority, task.estimated_turns
                    ) or ""
                    if commit_hash:
                        git.push()
                state_mgr.mark_completed(tid, commit_hash, task.output_files)
                state_mgr.save()
                snapshot_mgr.update_snapshot()
                knowledge_mgr.extract_and_append(
                    tid, task.name, task.category,
                    task.output_files, project_root,
                )
                print(f"  ✅ 完成 ({mins}m{secs}s)" +
                      (f" — {commit_hash}" if commit_hash else ""))
                return _TASK_OK
        else:
            # goose 退出失败 — 保留沙箱供排查
            if sandbox:
                logger.warning(f"Task {tid} failed, sandbox preserved at: {sandbox_path}")
            err = _build_structured_error(
                "goose_execution", result.returncode,
                f"goose exit {result.returncode}: {result.stderr[:500]}",
                task, sandbox_path, verify_env,
            )
            state_mgr.mark_failed_no_output(tid, err)
            state_mgr.save()
            print(f"  ❌ 失败 ({mins}m{secs}s)")

            tr = state_mgr.tasks[tid]
            action = handle_task_error(
                tid, task.name, tr["retries"],
                task.retry_limit, ai_dev_dir
            )

            if action == TaskAction.RETRY_TASK:
                state_mgr.tasks[tid]["status"] = STATUS_PENDING
                state_mgr.tasks[tid]["started_at"] = None
                state_mgr.save()
                return _TASK_RETRY
            elif action == TaskAction.SKIP_TASK:
                state_mgr.mark_skipped(tid, "Human skipped")
                state_mgr.save()
                return _TASK_SKIP
            elif action == TaskAction.ABORT_GRAPH:
                return _TASK_ABORT
            elif action == TaskAction.NOTE_EXIT:
                return _TASK_NOTE_EXIT
            return _TASK_SKIP  # fallback


def _build_structured_error(
    phase: str, goose_exit: int | None, error_detail: str,
    task: TaskConfig, sandbox_path: Path | None,
    verify_env: dict[str, str] | None,
    commands: list[str] | None = None,
) -> str:
    """构造结构化错误信息，便于事后诊断。

    包含阶段、goose 退出码、环境信息、文件存在性检查。
    """
    record: dict = {
        "phase": phase,
        "goose_exit_code": goose_exit,
        "error": error_detail,
        "declared_outputs": list(task.output_files),
    }
    if sandbox_path:
        record["files_on_disk"] = {
            f: (sandbox_path / f).exists()
            for f in task.output_files
        }
    if verify_env:
        record["env_java_home"] = verify_env.get("JAVA_HOME", "not set")
    if commands:
        record["verification_commands"] = commands
    try:
        return json.dumps(record, ensure_ascii=False, indent=2)
    except TypeError:
        return f"phase={phase} goose_exit={goose_exit} error={error_detail}"


def _write_context_file(ai_dev_dir: Path, task_id: str, context_text: str) -> str:
    """将组装好的上下文写入临时文件，供 goose session 读取。"""
    ctx_dir = ai_dev_dir / "task_contexts"
    ctx_dir.mkdir(exist_ok=True)
    ctx_file = ctx_dir / f"{task_id}.md"
    ctx_file.write_text(context_text, encoding="utf-8")
    return str(ctx_file)


def _module_bar(done: int, total: int) -> str:
    """渲染模块进度条。"""
    if total <= 0:
        return ""
    width = 12
    filled = int(width * done / total)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {done}/{total}"


def _detect_residual_files(project_root: Path, task: TaskConfig) -> list[str]:
    """检测上次崩溃残留的半成品输出文件。"""
    residual = []
    for f in task.output_files:
        fp = project_root / f
        if fp.exists():
            residual.append(f)
    return residual


VERIFY_TIMEOUT = 600  # 每步验证超时（秒）
_UNSAFE_SHELL_RE = re.compile(r'[;&|`$(){}\[\]!><\n\r]')  # shell 元字符检测


def _verify_java_home(java_home: str) -> bool:
    """Pre-flight 检查：验证 JAVA_HOME 路径下 java.exe 是否可执行。"""
    java_exe = os.path.join(java_home, "bin", "java.exe")
    try:
        result = subprocess.run(
            [java_exe, "-version"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False

# 子管线阶段定义：(名称, 目标描述, 轮次比例)
_SUB_PIPELINE_PHASES: list[tuple[str, str, float]] = [
    ("plan",   "生成模块实现方案，输出设计文档", 0.25),
    ("code",   "根据方案实现代码",               0.40),
    ("test",   "为实现的代码编写测试",           0.20),
    ("review", "审查代码和测试，修复发现的问题", 0.15),
]


def _run_sub_pipeline(
    *,
    tid: str,
    task: TaskConfig,
    base_params: dict[str, str],
    sandbox_path: Path,
    ai_dev_dir: Path,
    context_text: str,
    task_recipe: str,
    quiet: bool,
    on_timeout,
    env: dict[str, str] | None = None,
) -> tuple:
    """在沙箱内执行 mini-pipeline：方案→编码→测试→审查。

    每个阶段是独立的 goose session，分配合适的 turns。
    任一阶段失败则立即停止，保留沙箱供排查。

    Returns:
        (result, run_exception) — result 为最后一个阶段的 CompletedProcess 或失败时的 None
    """
    accumulated_context = context_text
    total_turns = task.estimated_turns

    for phase_idx, (phase_name, phase_goal, turn_fraction) in enumerate(_SUB_PIPELINE_PHASES):
        phase_turns = max(5, int(total_turns * turn_fraction))
        phase_timeout = max(5, int(task.timeout_minutes * turn_fraction))

        # 构建阶段专用上下文
        phase_context = (
            f"{accumulated_context}\n\n"
            f"---\n"
            f"## 当前阶段 ({phase_idx + 1}/{len(_SUB_PIPELINE_PHASES)}): {phase_name}\n"
            f"目标: {phase_goal}\n"
            f"---\n"
        )
        phase_ctx_file = _write_context_file(ai_dev_dir, f"{tid}_{phase_name}", phase_context)

        phase_params = {
            **base_params,
            "context_file": phase_ctx_file,
            "phase": phase_name,
            "phase_goal": phase_goal,
        }

        print(f"    📋 {phase_name} ({phase_turns} turns)...", flush=True)
        logger.info(f"Task {tid}: sub-pipeline phase {phase_name} ({phase_turns} turns)")

        try:
            result = run_task(
                recipe=task_recipe,
                max_turns=phase_turns,
                params=phase_params,
                cwd=sandbox_path,
                timeout_minutes=phase_timeout,
                on_timeout=on_timeout,
                quiet=quiet,
                env=env,
            )
        except Exception as e:
            logger.error(f"Task {tid}: sub-pipeline phase '{phase_name}' exception: {e}")
            return None, e

        if result.returncode != 0:
            logger.error(f"Task {tid}: sub-pipeline phase '{phase_name}' failed (exit {result.returncode})")
            print(f"    ❌ {phase_name} 失败", flush=True)
            return result, None

        print(f"    ✅ {phase_name} 完成", flush=True)

        # 将本阶段产出摘要追加到累积上下文，供下一阶段引用
        accumulated_context += (
            f"\n\n### 阶段 {phase_idx + 1} ({phase_name}) 完成\n"
            f"目标: {phase_goal}\n"
        )

    return result, None


def _resolve_verification_steps(
    task: TaskConfig, profile: dict | None,
) -> list[tuple[str, list[str]]]:
    """根据任务 verification 策略和 category 解析验证步骤。

    verification 值:
      - "auto": 根据 category 推断 — backend-api→backend, frontend→frontend, test→none
      - "backend": compileOnly + test（需要 profile.commands）
      - "frontend": frontendCheck（如 npm run build），profile 未提供则跳过
      - "none": 跳过

    返回 [(label, [cmd, ...]), ...] 或空列表。
    """
    mode = task.verification or "auto"
    category = (task.category or "").lower()

    # "auto" → 根据 category 推断
    if mode == "auto":
        if "frontend" in category:
            mode = "frontend"
        elif "backend" in category or "api" in category or "java" in category:
            mode = "backend"
        elif "test" in category:
            mode = "none"
        else:
            mode = "backend"  # 默认按后端处理

    if mode == "none":
        return []

    commands = (profile or {}).get("commands", {})

    if mode == "backend":
        steps: list[tuple[str, list[str]]] = []
        has_compile_only = "compileOnly" in commands
        has_build = "build" in commands
        has_test = "test" in commands
        if has_compile_only:
            steps.append(("compile", commands["compileOnly"]))
        elif has_build:
            steps.append(("build", commands["build"]))
        if has_test and has_compile_only:
            steps.append(("test", commands["test"]))
        return steps

    if mode == "frontend":
        if "frontendCheck" in commands:
            return [("frontend", commands["frontendCheck"])]
        # 未配置前端验证命令，跳过
        return []

    return []


def _get_verification_steps(profile: dict | None) -> list[tuple[str, list[str]]]:
    """后向兼容：旧调用默认按后端任务解析验证步骤。"""
    task = TaskConfig(
        id="_verification_probe",
        name="_verification_probe",
        description="",
        category="backend",
        verification="backend",
    )
    return _resolve_verification_steps(task, profile)


def _run_verification_step(
    sandbox_path: Path, label: str, commands: list[str],
    timeout: int = VERIFY_TIMEOUT, env: dict[str, str] | None = None,
) -> tuple[bool, str]:
    """在沙箱内执行一组验证命令。

    JAVA_HOME 通过 cmd /c 前缀注入（set + PATH），并做 pre-flight 检查。
    shell=True 场景下仅用命令前缀注入，不通过 env dict（避免 cmd /c 下的交互问题）。
    """
    java_home_prefix = ""
    if env:
        jh = env.get("JAVA_HOME", "")
        if jh:
            # Pre-flight：验证 java.exe 可执行
            if not _verify_java_home(jh):
                logger.warning(f"JAVA_HOME pre-flight failed: {jh}")
                return False, f"$ java -version\nJAVA_HOME 路径无效或 java.exe 不可执行: {jh}"
            # 命令前缀注入 JAVA_HOME + PATH（%JAVA_HOME%\bin 追加到 PATH）
            java_home_prefix = (
                f'set "JAVA_HOME={jh}" && '
                f'set "PATH={jh}\\bin;%PATH%" && '
            )
            logger.debug(f"Verification: JAVA_HOME={jh} (pre-flight OK)")
    for cmd in commands:
        # 安全检查：拒绝含 shell 元字符的命令（防 profile.yml 注入）
        if _UNSAFE_SHELL_RE.search(cmd):
            logger.error(f"Rejected unsafe verification command: {cmd[:120]}")
            return False, f"$ {cmd[:120]}\nREJECTED: command contains shell metacharacters"
        try:
            wrapped_cmd = f'{java_home_prefix}{cmd}'
            proc = subprocess.run(
                wrapped_cmd,
                cwd=str(sandbox_path),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            if proc.returncode != 0:
                tail = proc.stderr.strip() or proc.stdout.strip()
                lines = tail.splitlines()
                if len(lines) > 30:
                    tail = "\n".join(lines[-30:])
                return False, f"$ {cmd}\nexit {proc.returncode}\n{tail}"
        except subprocess.TimeoutExpired:
            return False, f"$ {cmd}\nTIMEOUT (>{timeout}s)"
    return True, f"$ {commands[-1]}\nOK"


def _detect_cycle(tasks: dict[str, TaskConfig]) -> list[str] | None:
    """DFS 检测循环依赖。返回循环路径或 None。"""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {tid: WHITE for tid in tasks}

    def dfs(node, path):
        color[node] = GRAY
        for dep in tasks[node].depends_on:
            if dep not in color:
                continue  # 外部依赖，跳过
            if color[dep] == GRAY:
                cycle_start = path.index(dep)
                return path[cycle_start:] + [dep]
            if color[dep] == WHITE:
                result = dfs(dep, path + [dep])
                if result:
                    return result
        color[node] = BLACK
        return None

    for tid in tasks:
        if color[tid] == WHITE:
            result = dfs(tid, [tid])
            if result:
                return result
    return None
