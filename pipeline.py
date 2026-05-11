#!/usr/bin/env python3
"""AI 全流程开发管线 — 主入口。

用法:
    python pipeline.py                          # 交互式启动
    python pipeline.py --project D:/MyPrj/xxx  # 指定项目路径
    python pipeline.py --resume                # 从断点恢复
    python pipeline.py --from-stage phase3     # 从指定阶段开始
    python pipeline.py --dry-run               # 预览将执行的阶段
"""

import sys
import os
import argparse
from pathlib import Path

# 确保项目根目录在 sys.path 中
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline import __version__
from pipeline.logger import init as init_logger
from pipeline.config import load_pipeline
from pipeline.state import (
    read_stage, write_stage, clear_stage,
    read_note, write_note, clear_note,
)
from pipeline.executor import check_goose, run_stage, GooseError, GooseNotFound
from pipeline.checkpoint import confirm, ask_boolean
from pipeline.error_handler import handle_error, Action

SEPARATOR = "=" * 60


def setup_project(project_path: str, req_file: str | None = None) -> tuple[Path, Path, Path]:
    """初始化目标项目的 .ai-dev 目录结构。"""
    p = Path(project_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"项目目录不存在: {p}")

    ad = p / ".ai-dev"
    out = ad / "outputs"
    ad.mkdir(exist_ok=True)
    out.mkdir(exist_ok=True)

    return p, ad, out


def expand_params(params: dict[str, str], P: Path, AD: Path, OUT: Path) -> dict[str, str]:
    """将参数模板中的占位符替换为实际路径。"""
    mapping = {
        "{P}": str(P),
        "{AD}": str(AD),
        "{OUT}": str(OUT),
    }
    expanded = {}
    for key, value in params.items():
        for placeholder, replacement in mapping.items():
            value = value.replace(placeholder, replacement)
        expanded[key] = value
    return expanded


def banner():
    """打印启动横幅。"""
    print(SEPARATOR)
    print(f"  AI Dev Flow v{__version__}")
    print("  需求 → 分析 → 方案 → 编码 → 审查 → 交付")
    print(SEPARATOR)


def main():
    parser = argparse.ArgumentParser(
        description="AI 全流程开发管线",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--project", "-p", help="目标项目路径")
    parser.add_argument("--req", "-r", help="需求文件路径")
    parser.add_argument("--resume", action="store_true", help="从断点恢复")
    parser.add_argument("--from-stage", dest="from_stage", help="从指定阶段开始")
    parser.add_argument("--dry-run", action="store_true", help="预览模式，不实际执行")
    parser.add_argument("--debug", action="store_true", help="调试模式")
    parser.add_argument("--version", action="version", version=f"ai-dev-flow v{__version__}")
    args = parser.parse_args()

    banner()

    # 交互式输入项目路径
    project_path = args.project
    if not project_path:
        project_path = input("项目路径: ").strip().strip('"')
        if not project_path:
            print("错误: 未指定项目路径")
            sys.exit(1)

    P, AD, OUT = setup_project(project_path)

    # 初始化日志
    logger = init_logger(P, debug=args.debug)
    logger.info(f"项目: {P}")

    # 验证 goose CLI
    try:
        check_goose()
    except GooseNotFound as e:
        logger.error(str(e))
        sys.exit(1)

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
    if not req_file:
        # 检查上一次运行是否有笔记
        note = read_note(AD)
        if note:
            print()
            print(SEPARATOR)
            print("  上次运行的笔记:")
            print(f"  {note}")
            print(SEPARATOR)
            if ask_boolean("清除笔记并继续?"):
                clear_note(AD)
            else:
                sys.exit(1)

        req_file = input("需求文件路径 (留空跳过): ").strip().strip('"')
        if req_file and Path(req_file).exists():
            import shutil
            dest = AD / "requirement-raw.md"
            shutil.copy(req_file, str(dest))
            logger.info(f"需求文件已复制到 {dest}")
            write_stage(AD, "input_done")

    # 确定起始阶段
    current_state = read_stage(AD)
    if args.from_stage:
        # 从指定阶段开始
        start_idx = 0
        for i, s in enumerate(pipeline.stages):
            if s.id == args.from_stage:
                start_idx = i
                break
        logger.info(f"从指定阶段开始: {pipeline.stages[start_idx].name}")
    elif current_state:
        start_idx = pipeline.find_resume_index(current_state)
        if start_idx >= len(pipeline.stages):
            logger.info("管线已全部完成!")
            clear_stage(AD)
            return
        if start_idx > 0:
            prev = pipeline.stages[start_idx - 1]
            logger.info(f"从断点恢复: {prev.name} 已完成，下一个: {pipeline.stages[start_idx].name}")
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

    # 执行管线
    total = len(pipeline.stages)
    for i in range(start_idx, total):
        stage = pipeline.stages[i]
        progress = f"[{i+1}/{total}]"

        if stage.is_checkpoint:
            prompt = expand_params({"_": stage.checkpoint_prompt}, P, AD, OUT)["_"]
            confirm(f"{progress} {stage.name}", prompt, AD)
            write_stage(AD, stage.state_value)
            continue

        # AI 阶段 — 带重试循环
        expanded_params = expand_params(stage.params, P, AD, OUT)
        recipe_path = str(PROJECT_ROOT / stage.recipe)

        while True:
            print()
            print(SEPARATOR)
            print(f"  {progress} {stage.name}")
            print(SEPARATOR)

            try:
                result = run_stage(
                    recipe=recipe_path,
                    max_turns=stage.max_turns,
                    params=expanded_params,
                    cwd=P,
                )

                if result.returncode == 0:
                    # 验证输出文件
                    if stage.output_file:
                        output_path = Path(expand_params(
                            {"_": stage.output_file}, P, AD, OUT
                        )["_"])
                        if not output_path.exists():
                            logger.warning(f"阶段完成但未生成预期文件: {output_path}")
                    write_stage(AD, stage.state_value)
                    logger.info(f"{stage.name} — 完成")
                    break
                else:
                    action = handle_error(AD)
                    if action == Action.RETRY:
                        continue
                    elif action == Action.NOTE_EXIT:
                        logger.info("已保存笔记，退出。下次运行将从该阶段继续。")
                        return
                    elif action == Action.SKIP:
                        write_stage(AD, stage.state_value)
                        logger.warning(f"{stage.name} — 已跳过")
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
                    break

    # 全部完成
    print()
    print(SEPARATOR)
    print("  管线全部完成!")
    print(SEPARATOR)
    clear_stage(AD)


if __name__ == "__main__":
    main()
