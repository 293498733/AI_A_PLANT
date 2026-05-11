"""人工确认检查点。"""

import logging
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")

SEPARATOR = "=" * 60


def confirm(title: str, prompt: str, ai_dev_dir: Path) -> None:
    """暂停并等待用户确认。"""
    print()
    print(SEPARATOR)
    print(f"  [人工确认] {title}")
    print(SEPARATOR)
    if prompt:
        print(f"  {prompt}")
        print(SEPARATOR)
    print()
    input("按 Enter 继续...")


def ask_boolean(prompt: str, default: bool = True) -> bool:
    """询问是/否问题。"""
    suffix = " (Y/n): " if default else " (y/N): "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")
