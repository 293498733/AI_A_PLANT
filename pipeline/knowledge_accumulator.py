"""知识积累器 — 从任务产出中自动提取关键决策，供下游任务参考。

知识库文件: .ai-dev/knowledge-base.md
格式：每个条目包含 task_id、category、timestamp、决策内容
"""

import re
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("ai-dev-flow")

KNOWLEDGE_FILE = "knowledge-base.md"
DECISION_HEADER_RE = re.compile(
    r'^##\s+(Key\s*Decisions?|关键决策|重要决策|Architecture\s*Decisions?)',
    re.IGNORECASE,
)
SECTION_BOUNDARY_RE = re.compile(r'^##\s+\w')


class KnowledgeAccumulator:
    """管理跨任务的决策知识积累与查询。"""

    def __init__(self, ai_dev_dir: Path):
        self.kb_path = ai_dev_dir / KNOWLEDGE_FILE
        if not self.kb_path.exists():
            self.kb_path.write_text(
                "# AI Dev Flow — 自动知识积累\n\n"
                "> 由管线自动生成，记录各任务的关键决策。下游任务自动参考。\n\n"
                "---\n\n",
                encoding="utf-8",
            )

    def extract_and_append(self, task_id: str, task_name: str, category: str,
                           output_files: list[str], project_root: Path) -> int:
        """扫描任务产出文件中的 Key Decisions 段落，追加到知识库。返回提取的条目数。"""
        decisions = []
        for fname in output_files:
            fp = project_root / fname
            if not fp.exists():
                continue
            try:
                content = fp.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            extracted = self._extract_decisions(content)
            if extracted:
                decisions.append((fname, extracted))

        if not decisions:
            return 0

        ts = datetime.now().strftime("%Y-%m-%d %H:%M")
        with self.kb_path.open("a", encoding="utf-8") as f:
            f.write(f"### [{task_id}] {task_name}\n")
            f.write(f"**Category**: {category} | **Time**: {ts}\n\n")
            for fname, lines in decisions:
                f.write(f"*From `{fname}`:*\n")
                for line in lines:
                    f.write(f"- {line}\n")
                f.write("\n")
            f.write("---\n\n")

        logger.info(f"Knowledge accumulated: {sum(len(d) for _, d in decisions)} decisions from task {task_id}")
        return sum(len(d) for _, d in decisions)

    def query(self, category: str, max_entries: int = 5) -> list[str]:
        """查询知识库中与指定 category 相关的条目。"""
        if not self.kb_path.exists():
            return []
        try:
            content = self.kb_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return []

        # 按 ### 条目分割
        entries = content.split("---")
        matches = []
        for entry in entries:
            entry = entry.strip()
            if not entry:
                continue
            # category 匹配或通用匹配
            if category and category.lower() in entry.lower():
                matches.append(entry)
            elif not category:
                matches.append(entry)

        return matches[-max_entries:]  # 最近的最相关

    def get_all(self) -> str:
        """读取完整知识库内容。"""
        if not self.kb_path.exists():
            return ""
        return self.kb_path.read_text(encoding="utf-8", errors="replace")

    # ---- Private ----

    def _extract_decisions(self, content: str) -> list[str]:
        """从文件内容中提取 Key Decisions 段落下的列表项。"""
        lines = content.splitlines()
        in_section = False
        decisions = []

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue

            if DECISION_HEADER_RE.match(stripped):
                in_section = True
                continue

            if in_section:
                if SECTION_BOUNDARY_RE.match(stripped):
                    break  # 进入下一个 ## 段落，停止
                if stripped.startswith(("- ", "* ", "1. ", "- [")):
                    decisions.append(stripped)

        return decisions
