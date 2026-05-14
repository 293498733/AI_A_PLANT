"""结构化日志模块 - 同时输出到终端和文件。"""

import logging
import sys
from pathlib import Path
from datetime import datetime

_LOGGER: logging.Logger | None = None
_LOG_FILE: Path | None = None


def init(project_root: Path, debug: bool = False) -> logging.Logger:
    global _LOGGER, _LOG_FILE

    log_dir = Path(project_root) / ".ai-dev" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    _LOG_FILE = log_dir / f"pipeline_{timestamp}.log"

    level = logging.DEBUG if debug else logging.INFO
    fmt = logging.Formatter("%(asctime)s [%(levelname)-5s] %(message)s", datefmt="%H:%M:%S")

    _LOGGER = logging.getLogger("ai-dev-flow")
    _LOGGER.setLevel(level)
    _LOGGER.handlers.clear()

    fh = logging.FileHandler(str(_LOG_FILE), encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    _LOGGER.addHandler(fh)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.WARNING)
    ch.setFormatter(TerminalFormatter())
    _LOGGER.addHandler(ch)

    cleaner = CleanupFilter()
    for h in _LOGGER.handlers:
        h.addFilter(cleaner)

    return _LOGGER


def get() -> logging.Logger:
    if _LOGGER is None:
        raise RuntimeError("Logger not initialized. Call pipeline.logger.init() first.")
    return _LOGGER


class CleanupFilter(logging.Filter):
    """过滤 AI 交互中可能出现的清理指令。"""
    def filter(self, record):
        msg = record.getMessage()
        blocked = [
            "清理上下文", "释放资源", "重置对话",
            "start fresh", "clean context", "clear context",
        ]
        for pattern in blocked:
            if pattern.lower() in msg.lower():
                return False
        return True


class TerminalFormatter(logging.Formatter):
    """终端输出带颜色标识。"""

    COLORS = {
        logging.DEBUG: "\033[36m",     # cyan
        logging.INFO: "\033[0m",        # default
        logging.WARNING: "\033[33m",    # yellow
        logging.ERROR: "\033[31m",      # red
        logging.CRITICAL: "\033[35m",   # magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{self.RESET}"
        if record.levelno >= logging.WARNING:
            record.msg = f"{color}{record.msg}{self.RESET}"
        return super().format(record)
