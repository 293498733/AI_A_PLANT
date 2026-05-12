from pathlib import Path
from pipeline.task_graph import (
    _detect_cycle, _module_bar, _detect_residual_files, _write_context_file,
)
from pipeline.config import TaskConfig


def _t(id, deps=None):
    return TaskConfig(id=id, name=id, description="", category="",
                      estimated_turns=20, priority="P0", depends_on=deps or [],
                      input_files=[], output_files=[], context_notes="",
                      reference_docs=[], module="")


class TestDetectCycle:
    def test_no_cycle_linear(self):
        tasks = {
            "a": _t("a"),
            "b": _t("b", ["a"]),
            "c": _t("c", ["b"]),
        }
        assert _detect_cycle(tasks) is None

    def test_simple_cycle(self):
        tasks = {
            "a": _t("a", ["b"]),
            "b": _t("b", ["a"]),
        }
        cycle = _detect_cycle(tasks)
        assert cycle is not None
        assert "a" in cycle and "b" in cycle

    def test_three_node_cycle(self):
        tasks = {
            "a": _t("a", ["b"]),
            "b": _t("b", ["c"]),
            "c": _t("c", ["a"]),
        }
        cycle = _detect_cycle(tasks)
        assert cycle is not None
        assert len(cycle) == 4  # a->b->c->a

    def test_external_dep_ignored(self):
        tasks = {"a": _t("a", ["external_task"])}
        assert _detect_cycle(tasks) is None

    def test_diamond_no_cycle(self):
        tasks = {
            "a": _t("a"),
            "b": _t("b", ["a"]),
            "c": _t("c", ["a"]),
            "d": _t("d", ["b", "c"]),
        }
        assert _detect_cycle(tasks) is None

    def test_self_loop(self):
        tasks = {"a": _t("a", ["a"])}
        cycle = _detect_cycle(tasks)
        assert cycle is not None


class TestModuleBar:
    def test_empty(self):
        assert _module_bar(0, 0) == ""

    def test_full(self):
        bar = _module_bar(5, 5)
        assert "5/5" in bar
        assert "░" not in bar

    def test_partial(self):
        bar = _module_bar(3, 10)
        assert "3/10" in bar
        assert "░" in bar
        assert "█" in bar

    def test_single_done(self):
        bar = _module_bar(1, 1)
        assert "1/1" in bar


class TestDetectResidualFiles:
    def test_existing_files_detected(self, tmp_path):
        (tmp_path / "out.py").write_text("x")
        task = TaskConfig(id="t", name="t", description="", category="",
                          estimated_turns=10, priority="P0", depends_on=[],
                          input_files=[], output_files=["out.py"],
                          context_notes="", reference_docs=[], module="")
        residual = _detect_residual_files(tmp_path, task)
        assert "out.py" in residual

    def test_no_residuals(self, tmp_path):
        task = TaskConfig(id="t", name="t", description="", category="",
                          estimated_turns=10, priority="P0", depends_on=[],
                          input_files=[], output_files=["missing.py"],
                          context_notes="", reference_docs=[], module="")
        assert _detect_residual_files(tmp_path, task) == []


class TestWriteContextFile:
    def test_writes_file_and_returns_path(self, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        result = _write_context_file(ad, "task-1", "# Context content")
        ctx_file = ad / "task_contexts" / "task-1.md"
        assert ctx_file.exists()
        assert ctx_file.read_text(encoding="utf-8") == "# Context content"
        assert "task-1.md" in result
