"""配置加载 - pipeline.yaml 和 profile.yml 解析。"""

import yaml
import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger("ai-dev-flow")


@dataclass
class StageConfig:
    id: str
    name: str
    recipe: str = ""
    max_turns: int = 0
    params: dict[str, str] = field(default_factory=dict)
    output_file: str | None = None
    is_checkpoint: bool = False
    checkpoint_prompt: str = ""
    state_value: str = ""


@dataclass
class PipelineConfig:
    stages: list[StageConfig]

    def find_resume_index(self, current_state: str) -> int:
        """根据当前状态找到应恢复的阶段索引。返回 -1 表示从头开始。"""
        if not current_state:
            return 0
        for i, stage in enumerate(self.stages):
            if stage.state_value == current_state:
                return i + 1
        logger.warning(f"unknown state '{current_state}', starting from beginning")
        return 0


def load_pipeline(path: Path) -> PipelineConfig:
    """从 pipeline.yaml 加载阶段定义。"""
    if not path.exists():
        raise FileNotFoundError(f"pipeline config not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    stages = []
    for item in data.get("stages", []):
        stages.append(StageConfig(
            id=item["id"],
            name=item["name"],
            recipe=item.get("recipe", ""),
            max_turns=item.get("max_turns", 0),
            params=item.get("params", {}),
            output_file=item.get("output_file"),
            is_checkpoint=item.get("is_checkpoint", False),
            checkpoint_prompt=item.get("checkpoint_prompt", ""),
            state_value=item["state_value"],
        ))

    logger.debug(f"loaded {len(stages)} stages from {path}")
    return PipelineConfig(stages=stages)


def load_profile(profile_path: Path) -> dict | None:
    """加载项目画像文件。"""
    if not profile_path.exists():
        return None
    with open(profile_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
