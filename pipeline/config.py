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
    is_task_graph: bool = False


@dataclass
class TaskConfig:
    """单个原子任务定义。"""
    id: str
    name: str
    description: str
    category: str = ""
    estimated_turns: int = 40
    priority: str = "P1"
    depends_on: list[str] = field(default_factory=list)
    input_files: list[str] = field(default_factory=list)
    output_files: list[str] = field(default_factory=list)
    context_notes: str = ""
    reference_docs: list[str] = field(default_factory=list)
    parallel_group: str | None = None
    retry_limit: int = 2
    timeout_minutes: int = 15


@dataclass
class TaskGraphConfig:
    """任务图定义。"""
    version: str = "1.0"
    project: str = ""
    created_at: str = ""
    total_estimated_turns: int = 0
    tasks: list[TaskConfig] = field(default_factory=list)


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
            is_task_graph=item.get("is_task_graph", False),
        ))

    logger.debug(f"loaded {len(stages)} stages from {path}")
    return PipelineConfig(stages=stages)


def load_task_graph(path: Path) -> TaskGraphConfig:
    """从 tasks.yaml 加载任务图定义。"""
    if not path.exists():
        raise FileNotFoundError(f"task graph config not found: {path}")

    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    tasks = []
    for item in data.get("tasks", []):
        tasks.append(TaskConfig(
            id=item["id"],
            name=item["name"],
            description=item["description"],
            category=item.get("category", ""),
            estimated_turns=item["estimated_turns"],
            priority=item.get("priority", "P1"),
            depends_on=item.get("depends_on", []),
            input_files=item.get("input_files", []),
            output_files=item.get("output_files", []),
            context_notes=item.get("context_notes", ""),
            reference_docs=item.get("reference_docs", []),
            parallel_group=item.get("parallel_group"),
            retry_limit=item.get("retry_limit", 2),
            timeout_minutes=item.get("timeout_minutes", 15),
        ))

    return TaskGraphConfig(
        version=data.get("version", "1.0"),
        project=data.get("project", ""),
        created_at=data.get("created_at", ""),
        total_estimated_turns=data.get("total_estimated_turns", 0),
        tasks=tasks,
    )


def load_profile(profile_path: Path) -> dict | None:
    """加载项目画像文件。"""
    if not profile_path.exists():
        return None
    with open(profile_path, encoding="utf-8") as f:
        return yaml.safe_load(f)
