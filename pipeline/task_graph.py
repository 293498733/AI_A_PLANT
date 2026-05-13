"""任务图执行器 — 依赖拓扑排序 + 逐任务 fresh session 执行（沙箱隔离）。"""

import time
import logging
from pathlib import Path

from pipeline.config import TaskGraphConfig, TaskConfig, load_task_graph
from pipeline.task_state import (
    TaskStateManager, STATUS_PENDING, STATUS_COMPLETED,
    STATUS_FAILED, STATUS_SKIPPED,
)
from pipeline.task_context import ContextAssembler
from pipeline.snapshot import SnapshotManager
from pipeline.knowledge_accumulator import KnowledgeAccumulator
from pipeline.git_ops import GitOps
from pipeline.executor import run_task
from pipeline.error_handler import handle_task_error, TaskAction
from pipeline.sandbox import SandboxManager, SandboxCreateError

logger = logging.getLogger("ai-dev-flow")

SEPARATOR = "=" * 60


def execute_task_graph(
    project_root: Path,
    ai_dev_dir: Path,
    tasks_file: Path,
    profile_path: Path,
    task_recipe: str = "recipes/steps/task-template.yaml",
) -> tuple[bool, dict]:
    """执行任务图。

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

    # 初始化状态管理器
    dependencies = {tid: t.depends_on for tid, t in tasks.items()}
    modules = {tid: t.module for tid, t in tasks.items() if t.module}
    state_mgr = TaskStateManager(ai_dev_dir, task_ids, dependencies, modules)
    state_mgr.reset_in_progress()  # 崩溃恢复

    # 清理上次崩溃可能留下的残留 sandbox
    SandboxManager.cleanup_orphaned(project_root, ai_dev_dir)

    # 自动跳过已耗尽重试的失败任务
    for tid in task_ids:
        tr = state_mgr.tasks[tid]
        if tr["status"] == STATUS_FAILED and tr["retries"] >= tasks[tid].retry_limit:
            logger.warning(f"Task {tid} retries exhausted ({tr['retries']}/{tasks[tid].retry_limit}), auto-skip")
            state_mgr.tasks[tid]["status"] = STATUS_SKIPPED
            state_mgr.tasks[tid]["notes"] = f"Auto-skipped: retries exhausted"
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
    print(SEPARATOR)

    total = len(graph.tasks)
    while True:
        # 计算已完成集合
        completed_ids: set[str] = set()
        for tid, tr in state_mgr.tasks.items():
            if tr["status"] in (STATUS_COMPLETED, STATUS_SKIPPED):
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
                state_mgr.tasks[tid]["status"] == STATUS_FAILED
                for tid in ready if tid in state_mgr.tasks
            ):
                # 有失败任务且没有就绪任务
                logger.error("Task graph blocked by failures")
                return False, state_mgr.tasks
            else:
                # Deadlock check
                pending = [tid for tid in task_ids
                           if state_mgr.tasks[tid]["status"] == STATUS_PENDING
                           and tid not in ready]
                # Check if pending tasks are truly blocked
                blocked = []
                for tid in pending:
                    task = tasks[tid]
                    unmet = [dep for dep in task.depends_on if dep not in completed_ids]
                    if any(state_mgr.tasks[dep]["status"] == STATUS_FAILED for dep in unmet):
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

        # 执行就绪任务（单线程顺序执行）
        for tid in ready:
            task = tasks[tid]
            tr = state_mgr.tasks[tid]

            print()
            print(SEPARATOR)
            print(f"  [{len(completed_ids)+1}/{total}] {task.name} ({task.id})")
            print(f"  分类: {task.category} | 优先级: {task.priority} | 预估: {task.estimated_turns}turns")
            if task.module:
                mod_prog = state_mgr.get_module_progress()
                if task.module in mod_prog:
                    d, t, f = mod_prog[task.module]
                    bar = _module_bar(d - (1 if f == 0 else 0), t)  # exclude current task
                    print(f"  模块: {task.module} {bar}")
            print(SEPARATOR)

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

            task_start = time.time()

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
                    sandbox = None  # 标记未使用沙箱

            # 构建参数（project_root 指向沙箱）
            params = {
                "task_name": task.name,
                "task_description": task.description,
                "project_root": str(sandbox_path),
                "profile": str(profile_path),
                "context_file": _write_context_file(ai_dev_dir, tid, context_text),
            }

            def _on_task_timeout():
                logger.error(f"Task {tid}: watchdog timeout, sandbox preserved at {sandbox_path}")

            try:
                result = run_task(
                    recipe=str(Path(__file__).resolve().parent.parent / task_recipe),
                    max_turns=task.estimated_turns,
                    params=params,
                    cwd=sandbox_path,
                    timeout_minutes=task.timeout_minutes,
                    on_timeout=_on_task_timeout,
                )

                elapsed = int(time.time() - task_start)
                mins, secs = divmod(elapsed, 60)

                if result.returncode == 0:
                    # 验证沙箱中的产出文件
                    missing = [f for f in task.output_files
                               if not (sandbox_path / f).exists()]
                    if missing:
                        logger.warning(f"Task {tid} completed but missing in sandbox: {missing}")
                        if sandbox:
                            logger.warning(f"Sandbox preserved at: {sandbox_path}")
                        state_mgr.mark_completed(tid, "", task.output_files)
                        state_mgr.save()
                        print(f"  ⚠️ 完成 ({mins}m{secs}s) — 但缺少文件: {missing}")
                    else:
                        # 检测非预期修改
                        if sandbox:
                            extra = sandbox.detect_extra_modifications(
                                set(task.output_files)
                            )
                            if extra:
                                logger.warning(f"Task {tid} modified undeclared files: {extra}")

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
                    completed_ids.add(tid)
                else:
                    # 失败 — 保留沙箱供排查
                    if sandbox:
                        logger.warning(f"Task {tid} failed, sandbox preserved at: {sandbox_path}")
                    state_mgr.mark_failed(tid,
                        f"goose exit {result.returncode}: {result.stderr[:200]}")
                    state_mgr.save()
                    print(f"  ❌ 失败 ({mins}m{secs}s)")

                    action = handle_task_error(
                        tid, task.name, tr["retries"],
                        task.retry_limit, ai_dev_dir
                    )

                    if action == TaskAction.RETRY_TASK:
                        state_mgr.tasks[tid]["status"] = STATUS_PENDING
                        state_mgr.tasks[tid]["started_at"] = None
                        state_mgr.save()
                        break  # 重新计算 ready 列表
                    elif action == TaskAction.SKIP_TASK:
                        state_mgr.mark_skipped(tid, "Human skipped")
                        state_mgr.save()
                        completed_ids.add(tid)
                    elif action == TaskAction.ABORT_GRAPH:
                        return False, state_mgr.tasks
                    elif action == TaskAction.NOTE_EXIT:
                        return False, state_mgr.tasks

            except Exception as e:
                logger.error(f"Task {tid} exception: {e}")
                if sandbox:
                    logger.warning(f"Task {tid} exception, sandbox preserved at: {sandbox_path}")
                state_mgr.mark_failed(tid, str(e))
                state_mgr.save()
                action = handle_task_error(
                    tid, task.name, tr["retries"],
                    task.retry_limit, ai_dev_dir
                )
                if action == TaskAction.RETRY_TASK:
                    state_mgr.tasks[tid]["status"] = STATUS_PENDING
                    state_mgr.save()
                    break
                elif action == TaskAction.ABORT_GRAPH:
                    return False, state_mgr.tasks
                elif action == TaskAction.NOTE_EXIT:
                    return False, state_mgr.tasks

    return True, state_mgr.tasks


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
