"""goose CLI 调用封装 — 实时输出、心跳、日志捕获。"""

import sys
import time
import shutil
import logging
import threading
import subprocess
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")

HEARTBEAT_INTERVAL = 60  # 无输出超过此秒数则打印心跳


class GooseError(Exception):
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"goose exited with code {returncode}")


class GooseNotFound(Exception):
    pass


def check_goose() -> str:
    goose = shutil.which("goose")
    if not goose:
        raise GooseNotFound(
            "goose CLI not found in PATH.\n"
            "Install: https://block.github.io/goose/"
        )
    logger.debug(f"goose found: {goose}")
    return goose


def build_params(params: dict[str, str]) -> list[str]:
    result = []
    for key, value in params.items():
        result.extend(["--params", f"{key}={value}"])
    return result


def run_stage(
    recipe: str,
    max_turns: int,
    params: dict[str, str],
    cwd: Path | None = None,
) -> subprocess.CompletedProcess:
    """执行 goose recipe，实时输出到终端并捕获到日志。"""

    recipe_name = Path(recipe).name
    args = [
        "goose", "run",
        "--recipe", recipe,
        "--max-turns", str(max_turns),
    ]
    args.extend(build_params(params))

    logger.info(f"goose run --recipe {recipe_name} --max-turns {max_turns}")
    logger.debug(f"params: {params}")

    proc = subprocess.Popen(
        args,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    stderr_lines: list[str] = []
    last_output = time.time()

    def _read_stderr():
        for line in proc.stderr:
            stripped = line.rstrip()
            if stripped:
                stderr_lines.append(stripped)
                logger.warning(f"[goose] {stripped}")

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    # 逐行读取 stdout，实时输出 + 写日志，附加心跳
    for raw_line in proc.stdout:
        last_output = time.time()
        line = raw_line.rstrip()
        if line:
            # 简洁输出到终端（goose 自身已有丰富输出，直接透传）
            print(line, flush=True)
            logger.debug(f"[goose] {line}")

    proc.wait()
    stderr_thread.join(timeout=5)

    if proc.returncode != 0:
        logger.error(f"goose exited with code {proc.returncode}")

    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode,
        stdout="",
        stderr="\n".join(stderr_lines),
    )


def run_task(
    recipe: str,
    max_turns: int,
    params: dict[str, str],
    cwd: Path,
    timeout_minutes: int = 15,
) -> subprocess.CompletedProcess:
    """执行单个任务。与 run_stage 相同流程，但附加超时控制。"""
    recipe_name = Path(recipe).name
    args = [
        "goose", "run",
        "--recipe", recipe,
        "--max-turns", str(max_turns),
    ]
    args.extend(build_params(params))

    logger.info(f"task: goose run --recipe {recipe_name} --max-turns {max_turns}")
    logger.debug(f"task params: {params}")

    try:
        proc = subprocess.Popen(
            args,
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise GooseNotFound("goose CLI not found in PATH")

    stderr_lines: list[str] = []

    def _read_stderr():
        for line in proc.stderr:
            stripped = line.rstrip()
            if stripped:
                stderr_lines.append(stripped)
                logger.warning(f"[goose] {stripped}")

    stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
    stderr_thread.start()

    for raw_line in proc.stdout:
        line = raw_line.rstrip()
        if line:
            print(line, flush=True)
            logger.debug(f"[goose] {line}")

    try:
        proc.wait(timeout=timeout_minutes * 60)
    except subprocess.TimeoutExpired:
        logger.error(f"Task timed out after {timeout_minutes} minutes")
        proc.kill()
        proc.wait()
        stderr_thread.join(timeout=5)
        return subprocess.CompletedProcess(
            args=args, returncode=-1,
            stdout="", stderr=f"Timeout after {timeout_minutes} minutes"
        )

    stderr_thread.join(timeout=5)

    if proc.returncode != 0:
        logger.error(f"goose exited with code {proc.returncode}")

    return subprocess.CompletedProcess(
        args=args,
        returncode=proc.returncode,
        stdout="",
        stderr="\n".join(stderr_lines),
    )
