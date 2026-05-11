"""goose CLI 调用封装。"""

import subprocess
import shutil
import logging
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")


class GooseError(Exception):
    def __init__(self, returncode: int, stderr: str = ""):
        self.returncode = returncode
        self.stderr = stderr
        super().__init__(f"goose exited with code {returncode}")


class GooseNotFound(Exception):
    pass


def check_goose() -> str:
    """验证 goose CLI 是否可用，返回 goose 路径。"""
    goose = shutil.which("goose")
    if not goose:
        raise GooseNotFound(
            "goose CLI not found in PATH.\n"
            "Install: https://block.github.io/goose/"
        )
    logger.debug(f"goose found: {goose}")
    return goose


def build_params(params: dict[str, str]) -> list[str]:
    """构建 goose --params 参数列表。"""
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
    """执行一个 goose recipe 阶段。"""
    args = [
        "goose", "run",
        "--recipe", recipe,
        "--max-turns", str(max_turns),
    ]
    args.extend(build_params(params))

    logger.info(f"executing: goose run --recipe {Path(recipe).name} --max-turns {max_turns}")
    logger.debug(f"params: {params}")

    result = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        capture_output=False,
        text=True,
    )

    if result.returncode != 0:
        logger.error(f"goose exited with code {result.returncode}")

    return result
