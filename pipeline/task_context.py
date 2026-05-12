"""上下文组装器 — 为每个任务构建独立的 goose 会话上下文。"""

import logging
from pathlib import Path

from pipeline.semantic_summarizer import SemanticSummarizer

logger = logging.getLogger("ai-dev-flow")

MAX_FILE_SIZE_FULL = 10 * 1024       # 10KB: 全文注入
MAX_FILE_SIZE_SLIM = 50 * 1024       # 50KB: 语义摘要模式


class TaskContext:
    """组装好的任务上下文。"""
    def __init__(self, task_name: str, task_description: str, context_notes: str,
                 input_contents: dict[str, str], doc_excerpts: dict[str, str]):
        self.task_name = task_name
        self.task_description = task_description
        self.context_notes = context_notes
        self.input_contents = input_contents
        self.doc_excerpts = doc_excerpts


class ContextAssembler:
    """读取任务指定的输入文件，组装上下文。支持增量扫描+语义摘要。"""

    def __init__(self, project_root: Path, ai_dev_dir: Path, snapshot_mgr=None):
        self.project_root = project_root
        self.outputs_dir = ai_dev_dir / "outputs"
        self._snapshot = snapshot_mgr
        self._changed_files: set[str] | None = None  # 当前变更集
        self._summarizer = SemanticSummarizer(ai_dev_dir)

    def _get_changed_set(self) -> set[str]:
        """获取自上次快照以来的变更文件集合（惰性初始化）。"""
        if self._changed_files is not None:
            return self._changed_files
        if self._snapshot:
            diff = self._snapshot.get_changed_files()
            self._changed_files = set(diff.added + diff.modified)
            if self._changed_files:
                logger.debug(f"Incremental scan: {len(self._changed_files)} changed files")
        else:
            self._changed_files = set()  # 无快照管理器时每次都读
        return self._changed_files

    def assemble(self, task) -> TaskContext:
        """为单个任务组装上下文。task 是 TaskConfig。"""
        changed = self._get_changed_set()

        input_contents: dict[str, str] = {}
        for file_path in task.input_files:
            full_path = self.project_root / file_path
            # 增量模式：仅变更文件重新读取，未变更用缓存
            if not self._snapshot or file_path in changed or not changed:
                content = self._read_file_smart(full_path)
                if content is not None:
                    input_contents[file_path] = content
                    if self._snapshot:
                        self._snapshot._content_cache[file_path] = content
            elif file_path in self._snapshot._content_cache:
                input_contents[file_path] = self._snapshot._content_cache[file_path]
            else:
                # 未变更但缓存缺失：首次读取并缓存
                content = self._read_file_smart(full_path)
                if content is not None:
                    input_contents[file_path] = content
                    self._snapshot._content_cache[file_path] = content

        doc_excerpts: dict[str, str] = {}
        for doc_name in task.reference_docs:
            doc_path = self.outputs_dir / doc_name
            # reference_docs 每次都读（通常是小文件且内容会变化）
            content = self._read_file_smart(doc_path)
            if content is not None:
                doc_excerpts[doc_name] = content

        return TaskContext(
            task_name=task.name,
            task_description=task.description,
            context_notes=task.context_notes,
            input_contents=input_contents,
            doc_excerpts=doc_excerpts,
        )

    def _read_file_smart(self, filepath: Path) -> str | None:
        """智能读取文件：
        - 小于 10KB：全文注入
        - 10KB 以上：语义结构提取（类/函数签名、关键注释、文档结构）
        摘要结果自动缓存到 .ai-dev/summaries/，同内容文件跳过重复提取。
        """
        if not filepath.exists():
            logger.debug(f"Context file not found: {filepath}")
            return None
        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        size = len(content.encode("utf-8"))
        if size <= MAX_FILE_SIZE_FULL:
            return content

        # 中大型文件：语义结构提取
        summary = self._summarizer.summarize(filepath)
        if summary:
            return summary

        # Fallback：摘要器无法处理时的简单截断
        lines = content.splitlines()
        return "\n".join(lines[:200])


    def render_prompt(self, task, ctx: TaskContext) -> str:
        """将组装的上下文渲染为任务 prompt 片段（供 recipe 的 context_notes 使用）。"""
        parts = [f"## Task: {ctx.task_name}\n\n{ctx.task_description}\n"]

        if ctx.context_notes:
            parts.append(f"### Implementation Context\n\n{ctx.context_notes}\n")

        if ctx.doc_excerpts:
            parts.append("### Reference Documents\n")
            for name, content in ctx.doc_excerpts.items():
                parts.append(f"#### {name}\n```\n{content[:2000]}\n```\n")

        if ctx.input_contents:
            parts.append("### Relevant Input Files\n")
            for path, content in ctx.input_contents.items():
                parts.append(f"#### {path}\n```\n{content[:3000]}\n```\n")

        return "\n".join(parts)
