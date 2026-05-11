"""人工确认检查点。"""

import logging
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")

SEPARATOR = "=" * 60
PREVIEW_LINES = 25


def confirm(title: str, prompt: str, preview_file: Path | None = None) -> None:
    """暂停并等待用户确认，可选展示产出文件摘要。"""
    print()
    print(SEPARATOR)
    print(f"  [人工确认] {title}")
    print(SEPARATOR)
    if prompt:
        print(f"  {prompt}")
        print(SEPARATOR)

    if preview_file and preview_file.exists():
        preview(preview_file)

    print()
    input("按 Enter 继续...")


def preview(filepath: Path, lines: int = PREVIEW_LINES) -> None:
    """展示文件的前 N 行作为摘要。"""
    try:
        content = filepath.read_text(encoding="utf-8")
        all_lines = content.splitlines()
        print()
        print(f"  --- {filepath.name} 摘要 (前 {min(lines, len(all_lines))} 行) ---")
        for line in all_lines[:lines]:
            print(f"  | {line}")
        if len(all_lines) > lines:
            print(f"  | ... (共 {len(all_lines)} 行，已省略)")
        print(f"  --- {filepath.stat().st_size // 1024}KB ---")
    except Exception:
        print(f"  (无法预览 {filepath.name})")


def ask_boolean(prompt: str, default: bool = True) -> bool:
    suffix = " (Y/n): " if default else " (y/N): "
    answer = input(prompt + suffix).strip().lower()
    if not answer:
        return default
    return answer in ("y", "yes")
