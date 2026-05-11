"""状态文件管理 - .pipeline_stage / .pipeline_note 读写。"""

import logging
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")

STAGE_FILE = ".pipeline_stage"
NOTE_FILE = ".pipeline_note"


def read_stage(ai_dev_dir: Path) -> str | None:
    """读取当前进度，无文件时返回 None。"""
    sf = ai_dev_dir / STAGE_FILE
    if not sf.exists():
        return None
    stage = sf.read_text(encoding="utf-8").strip()
    logger.debug(f"read stage: {stage}")
    return stage


def write_stage(ai_dev_dir: Path, stage: str) -> None:
    """写入当前进度。"""
    sf = ai_dev_dir / STAGE_FILE
    sf.write_text(stage, encoding="utf-8")
    logger.debug(f"write stage: {stage}")


def clear_stage(ai_dev_dir: Path) -> None:
    """删除状态文件（管线全部完成后）。"""
    sf = ai_dev_dir / STAGE_FILE
    if sf.exists():
        sf.unlink()
        logger.debug("stage file removed")


def read_note(ai_dev_dir: Path) -> str | None:
    """读取上次运行留下的笔记。"""
    nf = ai_dev_dir / NOTE_FILE
    if not nf.exists():
        return None
    return nf.read_text(encoding="utf-8").strip()


def write_note(ai_dev_dir: Path, note: str) -> None:
    """写入笔记。"""
    nf = ai_dev_dir / NOTE_FILE
    nf.write_text(note, encoding="utf-8")
    logger.info("note saved")


def clear_note(ai_dev_dir: Path) -> None:
    """删除笔记。"""
    nf = ai_dev_dir / NOTE_FILE
    if nf.exists():
        nf.unlink()
