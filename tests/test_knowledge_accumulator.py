from pathlib import Path
from pipeline.knowledge_accumulator import KnowledgeAccumulator


class TestExtractDecisions:
    def test_english_header(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## Key Decisions\n- use Redis\n- add cache layer\n"
        result = kb._extract_decisions(content)
        assert "- use Redis" in result
        assert "- add cache layer" in result

    def test_chinese_header(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## 关键决策\n- 使用 Redis\n- 添加缓存层\n"
        result = kb._extract_decisions(content)
        assert len(result) == 2

    def test_architecture_decisions_header(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## Architecture Decisions\n- Use microservices\n"
        result = kb._extract_decisions(content)
        assert len(result) == 1

    def test_section_boundary(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## Key Decisions\n- item 1\n## Next Section\n- not a decision\n"
        result = kb._extract_decisions(content)
        assert len(result) == 1
        assert "- item 1" in result

    def test_no_header_returns_empty(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "# Introduction\nSome text here\n"
        assert kb._extract_decisions(content) == []

    def test_varied_list_styles(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## Key Decisions\n- dash item\n* star item\n1. numbered item\n- [check] checked\n"
        result = kb._extract_decisions(content)
        assert len(result) == 4

    def test_empty_lines_skipped(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        content = "## Key Decisions\n\n- item 1\n\n- item 2\n"
        result = kb._extract_decisions(content)
        assert len(result) == 2


class TestInit:
    def test_creates_kb_file(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb = KnowledgeAccumulator(ad)
        kb_path = ad / "knowledge-base.md"
        assert kb_path.exists()
        content = kb_path.read_text(encoding="utf-8")
        assert "AI Dev Flow" in content

    def test_does_not_recreate_existing(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb_path = ad / "knowledge-base.md"
        kb_path.write_text("custom content", encoding="utf-8")
        KnowledgeAccumulator(ad)
        assert kb_path.read_text(encoding="utf-8") == "custom content"


class TestExtractAndAppend:
    def test_appends_decisions(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        out_file = tmp_path / "out.md"
        out_file.write_text("## Key Decisions\n- use Redis\n", encoding="utf-8")
        kb = KnowledgeAccumulator(ad)
        count = kb.extract_and_append("t1", "Test Task", "backend",
                                       ["out.md"], tmp_path)
        assert count == 1
        kb_content = ad / "knowledge-base.md"
        text = kb_content.read_text(encoding="utf-8")
        assert "[t1]" in text
        assert "use Redis" in text

    def test_missing_file_returns_zero(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb = KnowledgeAccumulator(ad)
        count = kb.extract_and_append("t1", "Task", "backend",
                                       ["nonexistent.md"], tmp_path)
        assert count == 0


class TestQuery:
    def test_filter_by_category(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb = KnowledgeAccumulator(ad)
        kb_path = ad / "knowledge-base.md"
        kb_path.write_text(
            "# KB\n\n### [t1] Backend Task\n**Category**: backend\n\n- Redis\n\n---\n\n"
            "### [t2] Frontend Task\n**Category**: frontend\n\n- Vue\n\n---\n\n",
            encoding="utf-8",
        )
        matches = kb.query("backend")
        assert len(matches) == 1
        assert "Redis" in matches[0]

    def test_empty_kb_returns_empty(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb = KnowledgeAccumulator(ad)
        assert kb.query("any") == []

    def test_no_category_matches_all(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb_path = ad / "knowledge-base.md"
        kb_path.write_text(
            "# KB\n\n### [t1] Task\n**Category**: core\n\n- item\n\n---\n\n",
            encoding="utf-8",
        )
        kb = KnowledgeAccumulator(ad)
        matches = kb.query("")
        assert len(matches) >= 1

    def test_max_entries_limit(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        chunks = []
        for i in range(10):
            chunks.append(f"### [t{i}] Task {i}\n**Category**: core\n\n- item {i}\n\n---\n")
        kb_path = ad / "knowledge-base.md"
        kb_path.write_text("# KB\n\n" + "\n".join(chunks), encoding="utf-8")
        kb = KnowledgeAccumulator(ad)
        matches = kb.query("core", max_entries=3)
        assert len(matches) <= 3


class TestGetAll:
    def test_returns_full_content(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        kb = KnowledgeAccumulator(ad)
        content = kb.get_all()
        assert "AI Dev Flow" in content

    def test_no_file_returns_empty(self, tmp_path):
        kb = KnowledgeAccumulator(tmp_path)
        assert kb.get_all() != ""
        # Simulate missing file by pointing to a non-existent path
        kb.kb_path = tmp_path / "nonexistent" / "nope.md"
        assert kb.get_all() == ""
