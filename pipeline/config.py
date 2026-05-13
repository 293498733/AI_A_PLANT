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
    module: str = ""          # 所属模块/子系统
    parallel_group: str | None = None
    sub_pipeline: bool = False  # 大模块内走 mini-pipeline（方案→编码→测试→审查）
    retry_limit: int = 2
    timeout_minutes: int = 15
    sandbox_enabled: bool = True  # 任务是否在 git worktree 沙箱中执行


@dataclass
class TaskGraphConfig:
    """任务图定义。"""
    version: str = "1.0"
    project: str = ""
    created_at: str = ""
    total_estimated_turns: int = 0
    max_workers: int = 3
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
        if "id" not in item:
            logger.warning(f"Skipping task without 'id': {item.get('name', str(item)[:80])}")
            continue
        tasks.append(TaskConfig(
            id=item["id"],
            name=item.get("name", item["id"]),
            description=item.get("description", ""),
            category=item.get("category", ""),
            estimated_turns=item.get("estimated_turns", 40),
            priority=item.get("priority", "P1"),
            depends_on=item.get("depends_on", []),
            input_files=item.get("input_files", []),
            output_files=item.get("output_files", []),
            context_notes=item.get("context_notes", ""),
            reference_docs=item.get("reference_docs", []),
            module=item.get("module", ""),
            parallel_group=item.get("parallel_group"),
            sub_pipeline=item.get("sub_pipeline", False),
            retry_limit=item.get("retry_limit", 2),
            timeout_minutes=item.get("timeout_minutes", 15),
            sandbox_enabled=item.get("sandbox_enabled", True),
        ))

    return TaskGraphConfig(
        version=data.get("version", "1.0"),
        project=data.get("project", ""),
        created_at=data.get("created_at", ""),
        total_estimated_turns=data.get("total_estimated_turns", 0),
        max_workers=data.get("max_workers", 3),
        tasks=tasks,
    )


def load_profile(profile_path: Path) -> dict | None:
    """加载项目画像文件。YAML 语法错误时自动修复重试一次；仍失败则回退到最小可用模板。"""
    if not profile_path.exists():
        return None
    with open(profile_path, encoding="utf-8") as f:
        text = f.read()
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        logger.warning("profile.yml has YAML syntax errors, attempting auto-repair")
        repaired = _repair_yaml(text)
        try:
            yaml.safe_load(repaired)
            profile_path.write_text(repaired, encoding="utf-8")
            logger.info("profile.yml auto-repaired and saved")
            return yaml.safe_load(repaired)
        except yaml.YAMLError as e:
            logger.warning(f"profile.yml repair failed, falling back to minimal template: {e}")
            fallback = _make_minimal_profile(text)
            profile_path.write_text(yaml.dump(fallback, allow_unicode=True), encoding="utf-8")
            logger.info("profile.yml replaced with minimal template")
            return fallback


def _repair_yaml(text: str) -> str:
    """修复 goose 生成 profile.yml 时的常见 YAML 语法错误：未加引号的值。"""
    import re
    lines = text.splitlines()
    fixed = []
    for line in lines:
        m = re.match(r'^(\s+)([\w-]+):\s+(.+)', line)
        if m and '\"' not in m.group(3).lstrip() and '\'' not in m.group(3).lstrip():
            val = m.group(3)
            if re.search(r'[(){}\[\]]|^@', val):
                val = val.replace('\"', '\\"')
                line = f'{m.group(1)}{m.group(2)}: "{val}"'
        fixed.append(line)
    return '\n'.join(fixed)


def _make_minimal_profile(text: str) -> dict:
    """从破损 YAML 中提取可用的 JDK/Framework 信息，构造最小可用 profile。"""
    import re
    profile: dict = {
        "profile": "java-spring",
        "description": "Auto-generated minimal profile (original YAML was unrepairable)",
        "projectRules": {},
        "backend": {"language": "Java", "jdk": {"compileRelease": 17}, "buildTool": "Maven"},
        "commands": {
            "compileOnly": ["mvn -DskipTests compile"],
            "test": ["mvn test"],
        },
    }

    # 尝试从 text 中提取 java.version
    m = re.search(r'<java\.version>(\d+)</java\.version>', text)
    if m:
        profile["backend"]["jdk"]["compileRelease"] = int(m.group(1))

    # 尝试从 text 中提取项目名
    m = re.search(r'profile:\s*(\S+)', text)
    if m:
        profile["profile"] = m.group(1)

    return profile
