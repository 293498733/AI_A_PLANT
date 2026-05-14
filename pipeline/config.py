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
    sandbox_enabled: bool = False  # 任务是否在 git worktree 沙箱中执行（默认关闭，稳定后再开启）


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


class EmptyTaskGraphError(Exception):
    """tasks.yaml 解析后无有效任务——可能因 YAML 语法错误或缺少 id 字段。"""


def load_task_graph(path: Path) -> TaskGraphConfig:
    """从 tasks.yaml 加载任务图定义。自动跳过无效任务并校验依赖引用。

    Raises:
        FileNotFoundError: tasks.yaml 不存在
        EmptyTaskGraphError: 文件存在但无法提取任何有效任务（YAML 语法错误或缺失 id 字段）
    """
    if not path.exists():
        raise FileNotFoundError(f"task graph config not found: {path}")

    with open(path, encoding="utf-8") as f:
        text = f.read()

    repair_attempted = False
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        logger.warning("tasks.yaml has YAML syntax errors, attempting auto-repair")
        repaired = _repair_yaml(text)
        repair_attempted = True
        try:
            data = yaml.safe_load(repaired)
            path.write_text(repaired, encoding="utf-8")
            logger.info("tasks.yaml auto-repaired and saved")
        except yaml.YAMLError as e:
            raise EmptyTaskGraphError(
                f"tasks.yaml YAML 语法错误无法自动修复: {e}\n"
                f"  文件: {path}\n"
                f"  建议: 检查 YAML 缩进、特殊字符引号、块标量语法"
            )

    tasks = []
    task_ids: set[str] = set()
    skipped = 0
    for item in data.get("tasks", []):
        if not isinstance(item, dict):
            # YAML 序列包含非映射项（如 bare string），报告并跳过
            logger.warning(f"Skipping non-mapping task entry: {str(item)[:100]}")
            skipped += 1
            continue
        tid = item.get("id")
        if not tid:
            logger.warning(f"Skipping task without 'id': {item.get('name', str(item)[:80])}")
            skipped += 1
            continue
        if tid in task_ids:
            logger.warning(f"Skipping duplicate task id: {tid}")
            skipped += 1
            continue
        task_ids.add(tid)

        # 校验 estimated_turns 合理范围
        turns = item.get("estimated_turns", 40)
        if not isinstance(turns, (int, float)) or turns < 1:
            logger.warning(f"Task {tid}: invalid estimated_turns={turns}, using 40")
            turns = 40
        if isinstance(turns, float):
            turns = int(turns)

        # 校验 priority
        priority = item.get("priority", "P1")
        if priority not in ("P0", "P1", "P2"):
            logger.warning(f"Task {tid}: invalid priority={priority}, using P1")
            priority = "P1"

        # 校验 output_files — 过滤 AI 幻觉的非文件路径（纯中文描述等）
        raw_outputs = item.get("output_files", [])
        valid_outputs = []
        for f in raw_outputs:
            if not isinstance(f, str) or not f.strip():
                continue
            if _looks_like_file_path(f):
                valid_outputs.append(f)
            else:
                logger.warning(
                    f"Task {tid}: output_file '{f}' does not look like a file path — "
                    f"likely an AI hallucination, skipping"
                )
        if len(valid_outputs) < len(raw_outputs):
            logger.warning(
                f"Task {tid}: filtered {len(raw_outputs) - len(valid_outputs)}/{len(raw_outputs)} "
                f"invalid output_files"
            )

        tasks.append(TaskConfig(
            id=tid,
            name=item.get("name", tid),
            description=item.get("description", ""),
            category=item.get("category", ""),
            estimated_turns=turns,
            priority=priority,
            depends_on=item.get("depends_on", []),
            input_files=item.get("input_files", []),
            output_files=valid_outputs,
            context_notes=item.get("context_notes", ""),
            reference_docs=item.get("reference_docs", []),
            module=item.get("module", ""),
            parallel_group=item.get("parallel_group"),
            sub_pipeline=item.get("sub_pipeline", False),
            retry_limit=item.get("retry_limit", 2),
            timeout_minutes=item.get("timeout_minutes", 15),
            sandbox_enabled=item.get("sandbox_enabled", False),
        ))

    if not tasks:
        raw_items = data.get("tasks", [])
        if raw_items:
            raise EmptyTaskGraphError(
                f"tasks.yaml 中 {len(raw_items)} 个条目均无法解析为有效任务\n"
                f"  文件: {path}\n"
                f"  已跳过: {skipped} 个\n"
                f"  常见原因: 任务条目缺少 'id:' 字段前缀\n"
                f"  示例: '- task-name' 应改为 '- id: task-name'"
            )
        raise EmptyTaskGraphError(
            f"tasks.yaml 中未定义任何任务\n"
            f"  文件: {path}\n"
            f"  修复后: {'已' if repair_attempted else '无'}自动修复"
        )

    # 后校验：检查 depends_on 引用的 task_id 是否存在
    for t in tasks:
        for dep in t.depends_on:
            if dep not in task_ids:
                logger.warning(f"Task {t.id}: depends_on '{dep}' does not exist — treating as external")

    if skipped:
        logger.warning(f"Skipped {skipped} invalid task(s) in {path}")

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
    """修复 goose 生成 YAML 时的常见语法错误。

    修复策略（按优先级）：
    1. bare task ID → - id: <bare-id>（缺 id: 前缀）
    2. 块标量 | > → 引号字符串
    3. 序列内联映射 - key: @value → 加引号
    4. 普通映射 key: @value → 加引号
    """
    import re
    lines = text.splitlines()
    # Pass 1: 修复缺少 id: 前缀的 bare task ID
    lines = _fix_bare_task_ids(lines)
    # Pass 2: 块标量 + 特殊字符引号修复
    fixed = []
    i = 0
    while i < len(lines):
        line = lines[i]
        # 检测块标量：key: | 或 key: >
        m_block = re.match(r'^(\s+)([\w-]+)\s*:\s*[|>]\s*$', line)
        if m_block:
            indent = len(m_block.group(1))
            key_indent = indent
            value_lines = []
            i += 1
            while i < len(lines):
                stripped = lines[i].rstrip()
                if not stripped or stripped.lstrip().startswith('#'):
                    i += 1
                    continue
                leading_spaces = len(lines[i]) - len(lines[i].lstrip())
                if leading_spaces <= key_indent:
                    break
                value_lines.append(stripped)
                i += 1
            escaped = '\\n'.join(value_lines).replace('"', '\\"')
            fixed.append(f'{m_block.group(1)}{m_block.group(2)}: "{escaped}"')
            continue

        # 修复 YAML 序列内联映射: - key: value（含 @ 等特殊字符）
        m_seq = re.match(r'^(\s+)-\s+([\w-]+):\s+(.+)', line)
        if m_seq and '\"' not in m_seq.group(3).lstrip() and '\'' not in m_seq.group(3).lstrip():
            val = m_seq.group(3)
            if _needs_quoting(val):
                val = val.replace('\"', '\\"')
                line = f'{m_seq.group(1)}- {m_seq.group(2)}: "{val}"'

        # 修复普通映射 key: value 中未加引号的值
        m = re.match(r'^(\s+)([\w-]+):\s+(.+)', line)
        if m and '\"' not in m.group(3).lstrip() and '\'' not in m.group(3).lstrip():
            val = m.group(3)
            if _needs_quoting(val):
                val = val.replace('\"', '\\"')
                line = f'{m.group(1)}{m.group(2)}: "{val}"'
        fixed.append(line)
        i += 1
    return '\n'.join(fixed)


def _looks_like_file_path(s: str) -> bool:
    """判断字符串是否像文件路径（而非 AI 幻觉的中文描述）。

    合法特征（满足任一即通过）：
    - 包含路径分隔符 / 或 \\
    - 有文件扩展名（.xx 后缀）
    - 是已知的占位符路径模式

    纯中文、无扩展名、无路径分隔符的字符串视为无效。
    """
    import re as _re
    s = s.strip()
    if not s:
        return False
    # 路径分隔符
    if "/" in s or "\\" in s:
        return True
    # 文件扩展名（.xxx，2-10 个字母数字）
    if _re.search(r'\.[a-zA-Z0-9]{1,10}$', s):
        return True
    # 纯中文且无路径结构 → AI 幻觉
    if _re.match(r'^[\u4e00-\u9fff\u3000-\u303f\uff00-\uffef（）()，。、《》？?！!：:；;]+$', s):
        return False
    # 兜底：如果有英文/数字混合，可能是合法文件名
    if _re.search(r'[a-zA-Z0-9]', s):
        return True
    return False


def _needs_quoting(val: str) -> bool:
    """检查 YAML 标量值是否需要引号包裹。

    跳过合法的 YAML flow sequence/mapping ([] 或 {})，这些不加引号。
    但包含 @ 等 YAML 保留字符的非 flow 值需要加引号。
    """
    import re as _re
    stripped = val.strip()
    # 合法的 YAML flow 结构，不引用
    if _re.match(r'^\[.*?\]$', stripped) or _re.match(r'^\{.*?\}$', stripped):
        return False
    return bool(_re.search(r'[(){}[\]@]', val))


def _fix_bare_task_ids(lines: list[str]) -> list[str]:
    """修复 YAML 序列中缺少 id: 前缀的 bare task ID。

    将:
      - task-something
        name: "..."
    转换为:
      - id: task-something
        name: "..."
    """
    import re
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^(\s+)-\s+([\w-]+)$', line)
        if m:
            current_indent = len(m.group(1))
            bare_value = m.group(2)
            # 检查下一行是否是更深的缩进 + key: value 映射
            if i + 1 < len(lines):
                next_line = lines[i + 1]
                next_indent = len(next_line) - len(next_line.lstrip())
                if next_indent > current_indent and re.match(r'\s+[\w-]+\s*:', next_line):
                    result.append(f'{m.group(1)}- id: {bare_value}')
                    i += 1
                    continue
        result.append(line)
        i += 1
    return result


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
