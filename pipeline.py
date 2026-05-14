#!/usr/bin/env python3
"""AI 全流程开发管线 — 主入口。

用法:
    python pipeline.py                          # 交互式启动
    python pipeline.py --project D:/MyPrj/xxx  # 指定项目路径
    python pipeline.py --project ./foo --git-url https://github.com/user/repo.git  # 自动 clone
    python pipeline.py --resume                # 从断点恢复
    python pipeline.py --from-stage phase3     # 从指定阶段开始
    python pipeline.py --dry-run               # 预览将执行的阶段
"""

import sys
import os
import time
import shutil
import argparse
import subprocess
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import __version__
from pipeline.logger import init as init_logger, get as get_logger
from pipeline.config import load_pipeline, load_profile as load_project_profile, EmptyTaskGraphError
from pipeline.state import (
    read_stage, write_stage, clear_stage,
    read_note, write_note, clear_note,
)
from pipeline.executor import check_goose, run_stage, GooseError, GooseNotFound, detect_jdk, JdkNotFound
from pipeline.checkpoint import confirm, ask_boolean, set_ci_mode as set_checkpoint_ci
from pipeline.error_handler import handle_error, Action, set_ci_mode as set_error_ci
from pipeline.task_graph import execute_task_graph
from pipeline.git_ops import GitOps

SEPARATOR = "=" * 60


def setup_project(project_path: str, git_url: str = "", git_branch: str = "") -> tuple[Path, Path, Path]:
    p = Path(project_path).resolve()
    if not p.exists():
        if git_url:
            print(f"项目目录不存在，从远程仓库 clone...")
            print(f"  {git_url} → {p}")
            p.parent.mkdir(parents=True, exist_ok=True)
            clone_cmd = ["git", "clone"]
            if git_branch:
                clone_cmd += ["-b", git_branch]
            clone_cmd += [git_url, str(p)]
            result = subprocess.run(
                clone_cmd,
                capture_output=True, text=True,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError(f"git clone 失败: {result.stderr.strip()}")
            print(f"  clone 完成")
        else:
            raise FileNotFoundError(f"项目目录不存在: {p}")

    ad = p / ".ai-dev"
    out = ad / "outputs"
    ad.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)

    return p, ad, out


def _clean_outputs(AD: Path, OUT: Path) -> None:
    """白名单保留式清理：仅保留 logs/，其余 .ai-dev/ 一级条目全部删除。"""
    import shutil as _shutil

    KEEP = {"logs"}  # 历史运行日志，排查问题唯一依据
    cleaned = []

    for entry in AD.iterdir():
        if entry.name in KEEP:
            continue
        try:
            if entry.is_dir():
                _shutil.rmtree(entry)
            else:
                entry.unlink()
            cleaned.append(entry.name + ("/" if entry.is_dir() else ""))
        except Exception as e:
            print(f"  警告: 无法删除 {entry.name}: {e}")

    if cleaned:
        print(f"  已清除: {', '.join(sorted(cleaned))}")


def expand_params(params: dict[str, str], P: Path, AD: Path, OUT: Path,
                  req_path: str = "") -> dict[str, str]:
    mapping = {
        "{P}": str(P),
        "{AD}": str(AD),
        "{OUT}": str(OUT),
        "{REQ}": req_path,
    }
    expanded = {}
    for key, value in params.items():
        for placeholder, replacement in mapping.items():
            value = value.replace(placeholder, replacement)
        expanded[key] = value
    return expanded


def _snapshot_outputs(OUT: Path) -> set[str]:
    """记录当前 outputs/ 中的文件名集合。"""
    if not OUT.exists():
        return set()
    return {f.name for f in OUT.iterdir() if f.is_file()}


def _detect_extra_files(OUT: Path, before: set[str], expected: set[str]) -> list[str]:
    """检测阶段执行后产生的非预期文件。"""
    after = _snapshot_outputs(OUT)
    new_files = after - before
    extra = [f for f in new_files if f not in expected]
    return extra


def banner():
    print(SEPARATOR)
    print(f"  AI Dev Flow v{__version__}")
    print("  需求 → 分析 → 方案 → 编码 → 审查 → 交付")
    print(SEPARATOR)


def _resolve_output_path(template: str | None, P: Path, AD: Path, OUT: Path) -> Path | None:
    """将占位符路径解析为实际 Path。"""
    if not template:
        return None
    resolved = expand_params({"_": template}, P, AD, OUT)["_"]
    return Path(resolved)


def main():
    parser = argparse.ArgumentParser(
        description="AI 全流程开发管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", "-p", help="目标项目路径")
    parser.add_argument("--git-url", help="远程仓库地址（项目目录不存在时自动 clone）")
    parser.add_argument("--git-branch", help="clone 时指定分支（配合 --git-url 使用）")
    parser.add_argument("--req", "-r", help="需求文件路径")
    parser.add_argument("--resume", action="store_true", help="从断点恢复")
    parser.add_argument("--new", dest="new_run", action="store_true", help="全新运行，清除旧的 .ai-dev 产出")
    parser.add_argument("--from-stage", dest="from_stage", help="从指定阶段开始")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际执行")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--verbose", action="store_true", help="goose 全量输出（默认 -q 静默，仅显示模型回复）")
    parser.add_argument("--ci", action="store_true", help="CI 模式，跳过所有人工交互，自动使用默认选择")
    parser.add_argument("--version", action="version", version=f"ai-dev-flow v{__version__}")
    args = parser.parse_args()

    if args.ci:
        set_checkpoint_ci(True)
        set_error_ci(True)

    banner()

    project_path = args.project
    if not project_path:
        if args.ci:
            print("错误: CI 模式需要指定 --project")
            sys.exit(1)
        project_path = input("项目路径: ").strip().strip('"')
        if not project_path:
            print("错误: 未指定项目路径")
            sys.exit(1)

    P, AD, OUT = setup_project(project_path,
                                git_url=args.git_url or "",
                                git_branch=args.git_branch or "")
    logger = init_logger(P, debug=args.debug)
    logger.info(f"项目: {P}")

    # 检测项目画像是否存在，不存在则强制从 Phase 0 开始
    profile_path = AD / "profile.yml"
    profile_missing = not profile_path.exists()
    if profile_missing:
        logger.info("项目画像不存在，将从 Phase 0 项目初始化开始")
        if not args.ci:
            print()
            print(SEPARATOR)
            print("  项目画像文件 (profile.yml) 不存在。")
            print("  将首先运行 Phase 0 — 自动扫描项目生成画像。")
            print(SEPARATOR)

    # 检测是否为全新需求提交
    existing_stage = read_stage(AD)
    has_outputs = list(OUT.glob("*")) if OUT.exists() else []

    if args.new_run and not args.from_stage:
        _clean_outputs(AD, OUT)
    elif args.new_run and args.from_stage:
        # from_stage 时不清除旧产出（需要之前阶段生成的文件）
        logger.info("--from-stage 模式，不清除旧产出")
    elif has_outputs and not existing_stage:
        print()
        print(SEPARATOR)
        print("  检测到旧的 .ai-dev 产出文件:")
        for f in sorted(has_outputs):
            print(f"    - {f.name}")
        print(SEPARATOR)
        if ask_boolean("清除旧文件开始全新运行?", default=True):
            _clean_outputs(AD, OUT)
        else:
            print("保留旧文件，继续执行（可能覆盖同名文件）")

    # 验证 goose CLI
    try:
        check_goose()
    except GooseNotFound as e:
        logger.error(str(e))
        sys.exit(1)

    # JDK 自动检测（供阶段级 goose 子进程使用）
    stage_env: dict[str, str] = {}
    try:
        _profile = load_project_profile(profile_path) if profile_path.exists() else None
        if _profile:
            jdk_required = int(_profile.get("backend", {}).get("jdk", {}).get("compileRelease", 17))
        else:
            jdk_required = 17
        jdk_home = detect_jdk(jdk_required)
        stage_env["JAVA_HOME"] = jdk_home
        logger.info(f"JDK {jdk_required} detected: {jdk_home}")
        print(f"  JDK 检测: {jdk_home}")
    except JdkNotFound as e:
        logger.warning(str(e))
    except Exception:
        pass  # profile 可能还不存在，Phase 0 会生成

    # 检查 API Key
    api_key = os.environ.get("CUSTOM_DEEPSEEK_API_KEY")
    if not api_key:
        logger.warning("未设置 CUSTOM_DEEPSEEK_API_KEY 环境变量")
        logger.warning("请运行: set CUSTOM_DEEPSEEK_API_KEY=你的key")
        if not ask_boolean("是否继续? (某些阶段可能无法正常工作)", default=False):
            sys.exit(1)

    # 加载管线配置
    pipeline_config_path = PROJECT_ROOT / "pipeline.yaml"
    pipeline = load_pipeline(pipeline_config_path)

    # 处理需求文件
    req_file = args.req
    if req_file:
        req_file = str(Path(req_file).resolve())
    else:
        note = read_note(AD)
        if note:
            print()
            print(SEPARATOR)
            print("  上次运行的笔记:")
            print(f"  {note}")
            print(SEPARATOR)
            choice = input("清除笔记并继续? (Y/n/保留笔记继续=q): ").strip().lower()
            if choice in ("", "y", "yes"):
                clear_note(AD)
            elif choice in ("q", "keep"):
                logger.info("保留笔记，继续执行")
            else:
                sys.exit(1)

        if not args.ci:
            req_file = input("需求文件路径 (留空跳过): ").strip().strip('"')
        if req_file:
            req_file = str(Path(req_file).resolve())

    # 确定起始阶段
    current_state = read_stage(AD)
    if args.from_stage:
        start_idx = 0
        for i, s in enumerate(pipeline.stages):
            if s.id == args.from_stage:
                start_idx = i
                break
        logger.info(f"从指定阶段开始: {pipeline.stages[start_idx].name}")
    elif profile_missing:
        start_idx = 0  # 强制从 Phase 0 开始
        logger.info("从 Phase 0 项目初始化开始（profile.yml 不存在）")
    elif current_state:
        start_idx = pipeline.find_resume_index(current_state)
        if start_idx >= len(pipeline.stages):
            logger.info("管线已全部完成!")
            clear_stage(AD)
            return
        if start_idx > 0:
            prev = pipeline.stages[start_idx - 1]
            logger.info(f"从断点恢复: {prev.name} 已完成 → {pipeline.stages[start_idx].name}")
        else:
            logger.info("开始全新管线")
    else:
        start_idx = 0
        logger.info("开始全新管线")

    if args.dry_run:
        print()
        print("预览模式 — 将执行以下阶段:")
        for i, s in enumerate(pipeline.stages[start_idx:], start=start_idx):
            marker = "[检查点]" if s.is_checkpoint else "[AI阶段]"
            print(f"  {i+1:2d}. {marker} {s.name}")
        return

    # 执行管线 — 记录各阶段耗时
    total = len(pipeline.stages)
    stage_times: list[tuple[str, float, str]] = []  # (name, elapsed_sec, status)
    pipeline_start = time.time()

    _tasks_snapshot = ""  # 任务图执行后保护 tasks.yaml 不被后续阶段覆盖

    for i in range(start_idx, total):
        stage = pipeline.stages[i]
        progress = f"[{i+1}/{total}]"
        stage_start = time.time()

        if stage.is_checkpoint:
            # 查找前一个阶段生成的产出文件作为预览
            preview_file = None
            for j in range(i - 1, -1, -1):
                prev_stage = pipeline.stages[j]
                if prev_stage.output_file:
                    preview_file = _resolve_output_path(prev_stage.output_file, P, AD, OUT)
                    break

            prompt_text = expand_params({"_": stage.checkpoint_prompt}, P, AD, OUT, req_file or "")["_"]
            confirm(f"{progress} {stage.name}", prompt_text, preview_file)
            write_stage(AD, stage.state_value)
            elapsed = time.time() - stage_start
            stage_times.append((stage.name, elapsed, "✅"))
            continue

        # Task Graph 阶段 — 路由到任务图执行器
        if stage.is_task_graph:
            expanded_params = expand_params(stage.params, P, AD, OUT, req_file or "")
            tasks_file = Path(expanded_params["tasks_file"])
            if not tasks_file.exists():
                logger.error(f"tasks.yaml 不存在: {tasks_file}")
                action = handle_error(AD)
                if action == Action.SKIP:
                    write_stage(AD, stage.state_value)
                    stage_times.append((stage.name, 0, "⚠️ 跳过"))
                    continue
                else:
                    return

            print()
            print(SEPARATOR)
            print(f"  {progress} {stage.name}")
            print(SEPARATOR)

            task_start = time.time()
            try:
                success, _ = execute_task_graph(
                    project_root=P,
                    ai_dev_dir=AD,
                    tasks_file=tasks_file,
                    profile_path=AD / "profile.yml",
                    task_recipe=expanded_params.get("task_recipe",
                        "recipes/steps/task-template.yaml"),
                    quiet=not args.verbose,
                )
            except EmptyTaskGraphError as e:
                logger.error(f"任务图加载失败: {e}")
                print(f"\n  ❌ 任务图为空，无法执行。")
                print(f"  {e}")
                action = handle_error(AD)
                if action == Action.SKIP:
                    elapsed = time.time() - task_start
                    stage_times.append((stage.name, elapsed, "❌ 空任务图"))
                    continue
                else:
                    return

            if success:
                write_stage(AD, stage.state_value)
                elapsed = time.time() - task_start
                mins, secs = divmod(int(elapsed), 60)
                logger.info(f"任务图执行完成 ({mins}m{secs}s)")
                stage_times.append((stage.name, elapsed, "✅"))
                _tasks_snapshot = tasks_file.read_text(encoding="utf-8") if tasks_file.exists() else ""
                continue
            else:
                action = handle_error(AD)
                if action == Action.RETRY:
                    continue
                elif action == Action.NOTE_EXIT:
                    return
                elif action == Action.SKIP:
                    write_stage(AD, stage.state_value)
                    elapsed = time.time() - task_start
                    stage_times.append((stage.name, elapsed, "⚠️ 跳过"))
                    _tasks_snapshot = tasks_file.read_text(encoding="utf-8") if tasks_file.exists() else ""
                    continue
                else:
                    return

        # AI 阶段 — 执行前恢复被覆盖的 tasks.yaml
        if _tasks_snapshot and tasks_file.exists():
            current = tasks_file.read_text(encoding="utf-8")
            if current != _tasks_snapshot:
                logger.warning("tasks.yaml was modified by a later phase, restoring original")
                tasks_file.write_text(_tasks_snapshot, encoding="utf-8")

        expanded_params = expand_params(stage.params, P, AD, OUT, req_file or "")
        recipe_path = str(PROJECT_ROOT / stage.recipe)
        before_files = _snapshot_outputs(OUT)

        # 预期文件集合
        expected_names = set()
        if stage.output_file:
            expected_path = _resolve_output_path(stage.output_file, P, AD, OUT)
            if expected_path:
                expected_names.add(expected_path.name)

        while True:
            print()
            print(SEPARATOR)
            print(f"  {progress} {stage.name}")
            print(SEPARATOR)
            print(f"  启动 goose (max {stage.max_turns} turns)...")
            print(SEPARATOR)

            try:
                result = run_stage(
                    recipe=recipe_path,
                    max_turns=stage.max_turns,
                    params=expanded_params,
                    cwd=P,
                    quiet=not args.verbose,
                    env=stage_env or None,
                )

                print()

                if result.returncode == 0:
                    # 验证预期输出文件
                    missing = []
                    if stage.output_file:
                        output_path = _resolve_output_path(stage.output_file, P, AD, OUT)
                        if output_path and not output_path.exists():
                            logger.warning(f"未生成预期文件: {output_path}")
                            missing.append(output_path.name)

                    # 检测额外产出文件
                    extra = _detect_extra_files(OUT, before_files, expected_names)
                    if extra:
                        logger.warning(f"检测到非预期产出文件: {extra}")
                        print(f"  [注意] AI 额外生成了非预期文件: {', '.join(extra)}")

                    if missing:
                        logger.error(f"缺少预期文件: {missing}")
                        action = handle_error(AD)
                        if action == Action.RETRY:
                            continue
                        elif action == Action.NOTE_EXIT:
                            return
                        elif action == Action.SKIP:
                            write_stage(AD, stage.state_value)
                            elapsed = time.time() - stage_start
                            stage_times.append((stage.name, elapsed, "⚠️ 跳过"))
                            break
                    else:
                        write_stage(AD, stage.state_value)
                        elapsed = time.time() - stage_start
                        mins = int(elapsed // 60)
                        secs = int(elapsed % 60)
                        logger.info(f"{stage.name} — 完成 ({mins}m{secs}s)")
                        stage_times.append((stage.name, elapsed, "✅"))
                        break
                else:
                    action = handle_error(AD)
                    if action == Action.RETRY:
                        continue
                    elif action == Action.NOTE_EXIT:
                        return
                    elif action == Action.SKIP:
                        write_stage(AD, stage.state_value)
                        elapsed = time.time() - stage_start
                        stage_times.append((stage.name, elapsed, "⚠️ 跳过"))
                        break

            except Exception as e:
                logger.error(f"执行异常: {e}")
                action = handle_error(AD)
                if action == Action.RETRY:
                    continue
                elif action == Action.NOTE_EXIT:
                    return
                elif action == Action.SKIP:
                    write_stage(AD, stage.state_value)
                    elapsed = time.time() - stage_start
                    stage_times.append((stage.name, elapsed, "⚠️ 异常"))
                    break

    # 全部完成 — 推送所有提交
    try:
        git = GitOps(P)
        git.push()
    except RuntimeError:
        pass  # 非 git 仓库，跳过

    total_elapsed = time.time() - pipeline_start
    clear_stage(AD)

    print()
    print(SEPARATOR)
    print("  管线全部完成!")
    print(SEPARATOR)
    _print_summary(stage_times, total_elapsed, OUT)


def _print_summary(stage_times: list[tuple[str, float, str]], total_elapsed: float, OUT: Path) -> None:
    """打印运行摘要。"""
    total_m = int(total_elapsed // 60)
    total_s = int(total_elapsed % 60)
    print()
    print(SEPARATOR)
    print(f"  运行摘要  (总耗时 {total_m}m{total_s}s)")
    print(SEPARATOR)
    for name, elapsed, status in stage_times:
        mins = int(elapsed // 60)
        secs = int(elapsed % 60)
        print(f"  {status}  {name:<12s}  {mins}m{secs}s")
    print(SEPARATOR)

    # 列出最终产出物
    if OUT.exists():
        outputs = sorted(OUT.iterdir())
        if outputs:
            print()
            print("  最终产出物:")
            for f in outputs:
                if f.is_file():
                    size_kb = f.stat().st_size // 1024
                    print(f"    - {f.name} ({size_kb}KB)")
            print()


if __name__ == "__main__":
    main()
