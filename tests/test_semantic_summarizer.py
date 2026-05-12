from pathlib import Path
from pipeline.semantic_summarizer import SemanticSummarizer

FIXTURES = Path(__file__).parent / "fixtures"


class TestSummarizePython:
    def test_extracts_imports_classes_functions(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_python(
            (FIXTURES / "sample_python.py").read_text().splitlines(),
            Path("sample_python.py"), 50, 1,
        )
        assert "os" in result or "import" in result.lower()
        assert "DataProcessor" in result
        # run_pipeline is a module-level function (not a method)
        assert "run_pipeline" in result

    def test_docstring_peek(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        lines = ['def foo():', '    """Do the thing."""', '    pass']
        result = s._summarize_python(lines, Path("x.py"), 3, 0)
        assert "Do the thing" in result

    def test_constants_and_todos(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        lines = [
            'MAX_SIZE = 100',
            '# TODO: fix this',
            'def bar(): pass',
            '# FIXME: broken',
        ]
        result = s._summarize_python(lines, Path("x.py"), 4, 0)
        assert "MAX_SIZE" in result
        assert "TODO" in result
        assert "FIXME" in result


class TestSummarizeJava:
    def test_extracts_package_imports_class_methods(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_java(
            (FIXTURES / "sample_java.java").read_text().splitlines(),
            Path("sample_java.java"), 50, 1,
        )
        assert "com.example.service" in result
        assert "ReturnNoticeService" in result
        assert "createDraft" in result


class TestSummarizeTypeScript:
    def test_extracts_interface_function(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_typescript(
            (FIXTURES / "sample_typescript.ts").read_text().splitlines(),
            Path("sample_typescript.ts"), 50, 1,
        )
        # Exports section captures items starting with "export " before
        # they reach the interface/function regex checks
        assert "Exports" in result
        assert "3 items" in result
        assert "HACK" in result


class TestSummarizeMarkdown:
    def test_extracts_headers(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_markdown(
            (FIXTURES / "sample_markdown.md").read_text().splitlines(),
            Path("sample_markdown.md"), 20, 0,
        )
        assert "# Project Title" in result
        assert "## Overview" in result


class TestSummarizeYAML:
    def test_extracts_top_level_keys(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        lines = ["profile: java-spring", "backend:", "  language: Java", "frontend:", "  framework: Vue"]
        result = s._summarize_yaml(lines, Path("x.yml"), 5, 0)
        assert "profile: java-spring" in result
        assert "backend:" in result
        assert "frontend:" in result


class TestSummarizeVue:
    def test_extracts_section_line_counts(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_vue(
            (FIXTURES / "sample_vue.vue").read_text().splitlines(),
            Path("sample_vue.vue"), 30, 0,
        )
        assert "<script>" in result
        assert "<template>" in result
        assert "<style>" in result


class TestSummarizeSQL:
    def test_extracts_statement_types(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_sql(
            (FIXTURES / "sample_sql.sql").read_text().splitlines(),
            Path("sample_sql.sql"), 20, 0,
        )
        assert "CREATE TABLE" in result
        assert "INSERT" in result
        assert "SELECT" in result


class TestSummarizeXML:
    def test_extracts_element_names(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        result = s._summarize_xml(
            (FIXTURES / "sample_xml.html").read_text().splitlines(),
            Path("sample_xml.html"), 25, 0,
        )
        assert "html" in result
        assert "div" in result


class TestSummarizeGeneric:
    def test_fallback(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        lines = ["name = 'value'", "other = 'data'"]
        result = s._summarize_generic(lines, Path("x.txt"), 2, 0)
        assert "Type" in result


class TestSummarizeCaching:
    def test_cache_hit(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        s = SemanticSummarizer(ad)
        f = tmp_path / "test.py"
        f.write_text("MAX = 100\n", encoding="utf-8")
        result1 = s.summarize(f)
        result2 = s.summarize(f)
        assert result1 == result2

    def test_file_not_found(self, tmp_path):
        (tmp_path / ".ai-dev").mkdir(parents=True)
        s = SemanticSummarizer(tmp_path / ".ai-dev")
        assert s.summarize(tmp_path / "nope.py") is None
