"""错误处理 - 4 选项交互。"""

import logging
from pathlib import Path
from enum import Enum

logger = logging.getLogger("ai-dev-flow")


class Action(Enum):
    RETRY = "retry"
    FIX = "fix"
    NOTE_EXIT = "note_exit"
    SKIP = "skip"


class TaskAction(Enum):
    RETRY_TASK = "retry_task"
    SKIP_TASK = "skip_task"
    ABORT_GRAPH = "abort_graph"
    NOTE_EXIT = "note_exit"


SEPARATOR = "=" * 60

ci_mode = False


def set_ci_mode(enabled: bool) -> None:
    global ci_mode
    ci_mode = enabled


def handle_error(ai_dev_dir: Path) -> Action:
    """显示错误菜单，返回用户选择的操作。"""
    if ci_mode:
        print("\n  [CI] 阶段执行失败，自动跳过...")
        return Action.SKIP
    print()
    print(SEPARATOR)
    print("  阶段执行失败")
    print(SEPARATOR)
    print()
    print("  1) retry      — 原地重试该阶段")
    print("  2) fix        — 手动修改后按任意键重试")
    print("  3) write note — 写说明笔记，保存并退出")
    print("  4) skip       — 跳过该阶段，标记为完成")
    print()

    while True:
        choice = input("  选择 (1/2/3/4): ").strip()

        if choice == "1":
            return Action.RETRY
        elif choice == "2":
            input("  修改完成后按 Enter 重试...")
            return Action.RETRY
        elif choice == "3":
            note = input("  写说明: ").strip()
            if note:
                note_path = ai_dev_dir / ".pipeline_note"
                note_path.write_text(note, encoding="utf-8")
                logger.info("笔记已保存，下次运行时会提示")
            return Action.NOTE_EXIT
        elif choice == "4":
            confirm = input("  确认跳过? 这会标记该阶段为已完成 (y/N): ").strip().lower()
            if confirm == "y":
                return Action.SKIP
        else:
            print("  无效输入，请输入 1/2/3/4")


def handle_task_error(task_id: str, task_name: str, retries: int,
                      retry_limit: int, ai_dev_dir: Path) -> TaskAction:
    """任务级错误处理菜单。返回用户选择的操作。"""
    if ci_mode:
        if retries < retry_limit:
            print(f"\n  [CI] Task {task_id} 失败 ({retries}/{retry_limit})，自动重试...")
            return TaskAction.RETRY_TASK
        else:
            print(f"\n  [CI] Task {task_id} 失败 (已达上限)，自动跳过...")
            return TaskAction.SKIP_TASK
    print()
    print(SEPARATOR)
    print(f"  Task Failed: {task_name} ({task_id})")
    print(f"  Retries: {retries}/{retry_limit}")
    print(SEPARATOR)
    print()
    if retries < retry_limit:
        print("  1) retry task — 重新执行此任务")
    else:
        print("  1) retry task — (已达重试上限)")
    print("  2) skip task — 跳过此任务，继续后续")
    print("  3) abort      — 终止任务图，保存进度")
    print("  4) write note — 写说明笔记并退出")
    print()

    while True:
        choice = input("  选择 (1/2/3/4): ").strip()

        if choice == "1":
            if retries >= retry_limit:
                print("  已达重试上限，请选择其他选项")
                continue
            return TaskAction.RETRY_TASK
        elif choice == "2":
            confirm = input("  确认跳过? 该任务产出将缺失 (y/N): ").strip().lower()
            if confirm == "y":
                return TaskAction.SKIP_TASK
        elif choice == "3":
            confirm = input("  确认终止任务图? (y/N): ").strip().lower()
            if confirm == "y":
                return TaskAction.ABORT_GRAPH
        elif choice == "4":
            note = input("  写说明: ").strip()
            if note:
                note_path = ai_dev_dir / ".pipeline_note"
                note_path.write_text(note, encoding="utf-8")
                logger.info("笔记已保存")
            return TaskAction.NOTE_EXIT
        else:
            print("  无效输入，请输入 1/2/3/4")
