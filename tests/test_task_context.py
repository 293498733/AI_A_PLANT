from pathlib import Path
from pipeline.task_context import TaskContext, ContextAssembler


class TestTaskContext:
    def test_dataclass(self):
        ctx = TaskContext(
            task_name="Test", task_description="Desc", context_notes="Notes",
            input_contents={"a.py": "print(1)"},
            doc_excerpts={"plan.md": "# Plan"},
        )
        assert ctx.task_name == "Test"
        assert ctx.input_contents["a.py"] == "print(1)"
        assert ctx.doc_excerpts["plan.md"] == "# Plan"


class TestRenderPrompt:
    def test_basic(self, tmp_path):
        ctx = TaskContext("MyTask", "Do something", "", {}, {})
        asm = ContextAssembler(Path("/tmp"), tmp_path)
        result = asm.render_prompt(None, ctx)
        assert "## Task: MyTask" in result
        assert "Do something" in result

    def test_with_context_notes(self, tmp_path):
        ctx = TaskContext("T", "D", "Use Redis for caching", {}, {})
        asm = ContextAssembler(Path("/tmp"), tmp_path)
        result = asm.render_prompt(None, ctx)
        assert "Use Redis for caching" in result

    def test_with_doc_excerpts(self, tmp_path):
        ctx = TaskContext("T", "D", "", {},
                          {"plan.md": "# Architecture\n\nUse microservices"})
        asm = ContextAssembler(Path("/tmp"), tmp_path)
        result = asm.render_prompt(None, ctx)
        assert "Reference Documents" in result
        assert "plan.md" in result

    def test_with_input_contents(self, tmp_path):
        ctx = TaskContext("T", "D", "", {"src/main.py": "print(1)"}, {})
        asm = ContextAssembler(Path("/tmp"), tmp_path)
        result = asm.render_prompt(None, ctx)
        assert "Relevant Input Files" in result
        assert "src/main.py" in result


class TestReadFileSmart:
    def test_small_file_full_content(self, tmp_path):
        (tmp_path / ".ai-dev").mkdir(parents=True)
        asm = ContextAssembler(tmp_path, tmp_path / ".ai-dev")
        f = tmp_path / "small.py"
        f.write_text("x = 1\ny = 2\n", encoding="utf-8")
        result = asm._read_file_smart(f)
        assert result == "x = 1\ny = 2\n"

    def test_large_file_uses_summarizer(self, tmp_path, mocker):
        ad = tmp_path / ".ai-dev"
        ad.mkdir(parents=True)
        asm = ContextAssembler(tmp_path, ad)
        mock_summary = "## File: big.py (5000 lines, 60KB)\n**Imports**: os, sys"
        mocker.patch.object(asm._summarizer, "summarize", return_value=mock_summary)
        # Create a file larger than 10KB
        big_content = "# Big file\n" + "x = 1\n" * 5000
        f = tmp_path / "big.py"
        f.write_text(big_content, encoding="utf-8")
        result = asm._read_file_smart(f)
        assert "big.py" in result

    def test_missing_file_returns_none(self, tmp_path):
        (tmp_path / ".ai-dev").mkdir(parents=True)
        asm = ContextAssembler(tmp_path, tmp_path / ".ai-dev")
        assert asm._read_file_smart(tmp_path / "nope.py") is None
