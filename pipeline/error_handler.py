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


SEPARATOR = "=" * 60


def handle_error(ai_dev_dir: Path) -> Action:
    """显示错误菜单，返回用户选择的操作。"""
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
