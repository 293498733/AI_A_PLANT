"""语义摘要器 — 从文件中提取结构化关键信息，替代纯截断。

策略（零 AI 成本）：
- 代码文件：提取类/函数签名、参数、返回类型、docstring、关键注释
- 文档文件：提取标题层级 + 首句摘要
- 配置文件：提取顶层结构
- 提取结果缓存到 .ai-dev/summaries/{hash}.md
"""

import re
import hashlib
import logging
from pathlib import Path

logger = logging.getLogger("ai-dev-flow")

SUMMARY_DIR = "summaries"
MAX_SUMMARY_LINES = 120  # 摘要最大行数


class SemanticSummarizer:
    """文件语义结构提取器。不调用 AI，基于语言规则提取关键信息。"""

    def __init__(self, ai_dev_dir: Path):
        self.cache_dir = ai_dev_dir / SUMMARY_DIR
        self.cache_dir.mkdir(exist_ok=True)

    def summarize(self, filepath: Path) -> str | None:
        """对文件做语义摘要。已在缓存中则直接返回。"""
        if not filepath.exists():
            return None

        try:
            content = filepath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        cache_key = hashlib.sha256(content.encode()).hexdigest()[:16]
        cache_file = self.cache_dir / f"{cache_key}.md"
        if cache_file.exists():
            return cache_file.read_text(encoding="utf-8")

        ext = filepath.suffix.lower()
        lines = content.splitlines()
        size_kb = len(content.encode("utf-8")) // 1024

        if ext in (".py", ".pyw"):
            summary = self._summarize_python(lines, filepath, len(lines), size_kb)
        elif ext in (".java", ".kt", ".scala"):
            summary = self._summarize_java(lines, filepath, len(lines), size_kb)
        elif ext in (".ts", ".tsx", ".js", ".jsx"):
            summary = self._summarize_typescript(lines, filepath, len(lines), size_kb)
        elif ext in (".md", ".mdx"):
            summary = self._summarize_markdown(lines, filepath, len(lines), size_kb)
        elif ext in (".yml", ".yaml"):
            summary = self._summarize_yaml(lines, filepath, len(lines), size_kb)
        elif ext in (".vue", ".svelte"):
            summary = self._summarize_vue(lines, filepath, len(lines), size_kb)
        elif ext in (".xml", ".html", ".htm"):
            summary = self._summarize_xml(lines, filepath, len(lines), size_kb)
        elif ext in (".sql"):
            summary = self._summarize_sql(lines, filepath, len(lines), size_kb)
        else:
            summary = self._summarize_generic(lines, filepath, len(lines), size_kb)

        cache_file.write_text(summary, encoding="utf-8")
        return summary

    # ---- Python ----

    def _summarize_python(self, lines: list[str], filepath: Path,
                          total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        imports, classes, funcs, constants, comments = [], [], [], [], []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            # Imports
            if stripped.startswith(("import ", "from ")):
                imports.append(stripped)
            # Class defs
            elif stripped.startswith("class "):
                doc = self._peek_docstring(lines, i)
                classes.append(f"- `{stripped}`{doc}")
            # Function defs (not methods — those are indented)
            elif stripped.startswith("def ") and not line.startswith((" ", "\t")):
                doc = self._peek_docstring(lines, i)
                funcs.append(f"- `{stripped}`{doc}")
            # Decorators (capture before class/def)
            elif stripped.startswith("@"):
                if i < total and lines[i].strip().startswith(("class ", "def ")):
                    continue  # will be captured with the class/def
            # Module-level constants
            elif re.match(r'^[A-Z_][A-Z0-9_]*\s*=', stripped):
                constants.append(stripped.split("=")[0].strip())
            # Key comments
            elif re.search(r'(TODO|FIXME|HACK|XXX|NOTE|WARNING)', stripped, re.I):
                comments.append(f"  L{i}: {stripped[:100]}")

        if imports:
            parts.append(f"**Imports**: {', '.join(imports[:15])}")
            if len(imports) > 15:
                parts.append(f"  ... and {len(imports) - 15} more")
        if constants:
            parts.append(f"**Constants**: {', '.join(constants[:20])}")
        if classes:
            parts.append(f"\n### Classes ({len(classes)})")
            parts.extend(classes[:30])
            if len(classes) > 30:
                parts.append(f"  ... and {len(classes) - 30} more")
        if funcs:
            parts.append(f"\n### Functions ({len(funcs)})")
            parts.extend(funcs[:30])
            if len(funcs) > 30:
                parts.append(f"  ... and {len(funcs) - 30} more")
        if comments:
            parts.append("\n### Key Comments")
            parts.extend(comments[:15])

        return "\n".join(parts)

    # ---- Java/Kotlin ----

    def _summarize_java(self, lines: list[str], filepath: Path,
                        total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        package, imports, classes, methods, fields, comments = "", [], [], [], [], []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("package "):
                package = stripped
            elif stripped.startswith("import "):
                imports.append(stripped)
            elif re.match(r'(public |private |protected )?(class |interface |@interface |enum )', stripped):
                classes.append(f"- `{stripped}`")
            elif re.match(r'(public |private |protected )?[\w<>\[\],\s]+\s+\w+\s*\(', stripped):
                methods.append(f"- `{stripped[:120]}`")
            elif re.match(r'(public |private |protected )?static\s+final\s+', stripped):
                fields.append(stripped[:80])
            elif re.search(r'(TODO|FIXME|HACK|XXX)', stripped, re.I):
                comments.append(f"  L{i}: {stripped[:100]}")

        if package:
            parts.append(f"**Package**: {package}")
        if imports:
            parts.append(f"**Imports**: {len(imports)} packages")
        if classes:
            parts.append(f"\n### Classes/Interfaces ({len(classes)})")
            parts.extend(classes)
        if fields:
            parts.append("\n### Constants/Fields")
            parts.extend(fields[:15])
        if methods:
            parts.append(f"\n### Methods ({len(methods)})")
            parts.extend(methods[:40])
            if len(methods) > 40:
                parts.append(f"  ... and {len(methods) - 40} more")
        if comments:
            parts.append("\n### Key Comments")
            parts.extend(comments[:15])

        return "\n".join(parts)

    # ---- TypeScript/JavaScript ----

    def _summarize_typescript(self, lines: list[str], filepath: Path,
                              total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        imports, exports, classes, funcs, interfaces, comments = [], [], [], [], [], []

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("import "):
                imports.append(stripped[:80])
            elif stripped.startswith("export "):
                exports.append(stripped[:100])
            elif stripped.startswith("class "):
                classes.append(f"- `{stripped[:120]}`")
            elif re.match(r'(export\s+)?(interface|type)\s+', stripped):
                interfaces.append(f"- `{stripped[:120]}`")
            elif re.match(r'(export\s+)?(async\s+)?function\s+', stripped):
                funcs.append(f"- `{stripped[:120]}`")
            elif re.search(r'(TODO|FIXME|HACK|XXX)', stripped, re.I):
                comments.append(f"  L{i}: {stripped[:100]}")

        if imports:
            parts.append(f"**Imports**: {len(imports)} modules")
        if exports:
            parts.append(f"**Exports**: {len(exports)} items")
        if interfaces:
            parts.append(f"\n### Interfaces/Types ({len(interfaces)})")
            parts.extend(interfaces[:20])
        if classes:
            parts.append(f"\n### Classes ({len(classes)})")
            parts.extend(classes[:20])
        if funcs:
            parts.append(f"\n### Functions ({len(funcs)})")
            parts.extend(funcs[:30])
        if comments:
            parts.append("\n### Key Comments")
            parts.extend(comments[:15])

        return "\n".join(parts)

    # ---- Markdown ----

    def _summarize_markdown(self, lines: list[str], filepath: Path,
                            total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        headers = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("#"):
                headers.append(stripped)
        if headers:
            parts.append("### Document Structure")
            parts.extend(headers[:40])
            if len(headers) > 40:
                parts.append(f"  ... and {len(headers) - 40} more headings")
        return "\n".join(parts)

    # ---- YAML ----

    def _summarize_yaml(self, lines: list[str], filepath: Path,
                        total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        top_keys = []
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and not line.startswith(" "):
                top_keys.append(stripped[:100])
        if top_keys:
            parts.append("### Top-level Structure")
            parts.extend(f"- {k}" for k in top_keys[:30])
        return "\n".join(parts)

    # ---- Vue/Svelte ----

    def _summarize_vue(self, lines: list[str], filepath: Path,
                       total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        sections = []
        in_script, in_style, in_template = False, False, False
        script_lines, style_lines, template_lines = 0, 0, 0

        for line in lines:
            stripped = line.strip()
            if "<script" in stripped:
                in_script = True
            elif "</script>" in stripped:
                in_script = False
                sections.append(f"- `<script>` ({script_lines} lines)")
            elif "<style" in stripped:
                in_style = True
            elif "</style>" in stripped:
                in_style = False
                sections.append(f"- `<style>` ({style_lines} lines)")
            elif "<template" in stripped:
                in_template = True
            elif "</template>" in stripped:
                in_template = False
                sections.append(f"- `<template>` ({template_lines} lines)")
            elif in_script:
                script_lines += 1
            elif in_style:
                style_lines += 1
            elif in_template:
                template_lines += 1

        if sections:
            parts.append("### Component Structure")
            parts.extend(sections)
        return "\n".join(parts)

    # ---- XML/HTML ----

    def _summarize_xml(self, lines: list[str], filepath: Path,
                       total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        tags = set()
        for line in lines:
            for m in re.finditer(r'<(\w+)', line):
                tags.add(m.group(1))
        if tags:
            parts.append(f"**Elements**: {', '.join(sorted(tags)[:30])}")
        return "\n".join(parts)

    # ---- SQL ----

    def _summarize_sql(self, lines: list[str], filepath: Path,
                       total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        statements = []
        for line in lines:
            stripped = line.strip().upper()
            if re.match(r'(CREATE|ALTER|DROP|INSERT|UPDATE|DELETE|SELECT|GRANT|REVOKE)\b', stripped):
                statements.append(stripped[:120])
        if statements:
            parts.append("### SQL Statements")
            parts.extend(f"- {s}" for s in statements[:20])
            if len(statements) > 20:
                parts.append(f"  ... and {len(statements) - 20} more")
        return "\n".join(parts)

    # ---- Generic fallback ----

    def _summarize_generic(self, lines: list[str], filepath: Path,
                           total: int, size_kb: int) -> str:
        parts = [f"## File: {filepath.name} ({total} lines, {size_kb}KB)\n"]
        parts.append(f"**Type**: {filepath.suffix or 'text'}")
        # Extract lines that look like declarations
        decls = []
        for line in lines[:200]:
            stripped = line.strip()
            if stripped and not stripped.startswith(("#", "//", "/*", "*")):
                if re.match(r'^[\w]+\s+[\w]+\s*[=(]', stripped):
                    decls.append(stripped[:120])
        if decls:
            parts.append("### Possible Declarations")
            parts.extend(f"- {d}" for d in decls[:30])
        return "\n".join(parts)

    # ---- Helpers ----

    def _peek_docstring(self, lines: list[str], idx: int) -> str:
        """提取紧随定义行的 docstring 首行。"""
        if idx >= len(lines):
            return ""
        next_line = lines[idx].strip()
        # 单行 docstring: """text""" 或 '''text'''
        m = re.match(r'["\']{3}(.+?)["\']{3}', next_line)
        if m:
            return f' — "{m.group(1)[:80]}"'
        # 多行 docstring 开始
        if next_line.startswith(('"""', "'''")):
            text = next_line.lstrip('"').lstrip("'").strip()
            if text:
                return f' — "{text[:80]}"'
        return ""
