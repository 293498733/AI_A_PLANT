"""Integration tests — marked with @pytest.mark.integration, skipped by default.

Run with: pytest tests/ -m integration
"""
import pytest
from pathlib import Path

from pipeline.config import load_pipeline, load_task_graph, load_profile
from pipeline.task_state import (
    TaskStateManager, STATUS_PENDING, STATUS_COMPLETED, STATUS_SKIPPED,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTPROJ = Path(__file__).parent / "testproj"


@pytest.mark.integration
class TestRealPipelineConfig:
    def test_parses_without_error(self):
        cfg = load_pipeline(PROJECT_ROOT / "pipeline.yaml")
        assert len(cfg.stages) >= 10
        # Verify Phase 0 is first
        assert cfg.stages[0].id == "phase0"
        # Verify task_graph stage exists
        task_graph_stages = [s for s in cfg.stages if s.is_task_graph]
        assert len(task_graph_stages) == 1

    def test_all_stages_have_state_value(self):
        cfg = load_pipeline(PROJECT_ROOT / "pipeline.yaml")
        for s in cfg.stages:
            assert s.state_value, f"Stage {s.id} missing state_value"
            if s.is_checkpoint:
                assert s.checkpoint_prompt, f"Checkpoint {s.id} missing prompt"


@pytest.mark.integration
class TestRealProfileConfig:
    def test_parses_without_error(self):
        profile = load_profile(PROJECT_ROOT / "profiles" / "java-spring.yml")
        assert profile is not None
        assert "profile" in profile
        assert "backend" in profile
        assert "commands" in profile


@pytest.mark.integration
class TestTaskStateFullLifecycle:
    def test_three_task_chain(self, tmp_path):
        """Simulate full task graph execution: A → B → C."""
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (ad / "outputs").mkdir()

        deps = {"a": [], "b": ["a"], "c": ["b"]}
        mods = {"a": "core", "b": "core", "c": "ui"}
        mgr = TaskStateManager(ad, ["a", "b", "c"], deps, mods)

        # First wave: only A is ready
        ready = mgr.get_next_ready(set())
        assert ready == ["a"]

        # Execute A
        mgr.mark_in_progress("a")
        mgr.mark_completed("a", "abc123", ["a.py"])
        mgr.save()

        # Second wave: B is ready
        ready = mgr.get_next_ready({"a"})
        assert ready == ["b"]

        # Execute B
        mgr.mark_in_progress("b")
        mgr.mark_completed("b", "def456", ["b.py"])

        # Third wave: C is ready
        ready = mgr.get_next_ready({"a", "b"})
        assert ready == ["c"]

        # Execute C
        mgr.mark_in_progress("c")
        mgr.mark_skipped("c", "not needed")

        # Verify final state
        done, total, failed = mgr.progress()
        assert done == 3
        assert total == 3
        assert failed == 0

        # Verify module progress
        prog = mgr.get_module_progress()
        assert prog["core"] == (2, 2, 0)
        assert prog["ui"] == (1, 1, 0)

    def test_persistence_roundtrip(self, tmp_path):
        """TaskStateManager saves and reloads correctly."""
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        (ad / "outputs").mkdir()

        mgr1 = TaskStateManager(ad, ["t1", "t2"], {"t1": ["t2"]}, {})
        mgr1.mark_in_progress("t2")
        mgr1.mark_completed("t2", "hash1", ["out.py"])
        mgr1.save()

        # Reload
        mgr2 = TaskStateManager(ad, ["t1", "t2"], {"t1": ["t2"]}, {})
        assert mgr2.tasks["t2"]["status"] == STATUS_COMPLETED
        assert mgr2.tasks["t2"]["commit_hash"] == "hash1"
        assert mgr2.tasks["t1"]["status"] == STATUS_PENDING


@pytest.mark.integration
class TestCycleDetectionWithRealisticGraph:
    def test_complex_dag_no_cycle(self):
        from pipeline.task_graph import _detect_cycle
        from pipeline.config import TaskConfig

        tasks = {
            "init": TaskConfig(id="init", name="Init", description="",
                               category="", estimated_turns=10, priority="P0",
                               depends_on=[], input_files=[], output_files=[],
                               context_notes="", reference_docs=[], module=""),
            "backend": TaskConfig(id="backend", name="Backend", description="",
                                  category="", estimated_turns=50, priority="P0",
                                  depends_on=["init"], input_files=[], output_files=[],
                                  context_notes="", reference_docs=[], module=""),
            "frontend": TaskConfig(id="frontend", name="Frontend", description="",
                                   category="", estimated_turns=40, priority="P0",
                                   depends_on=["init"], input_files=[], output_files=[],
                                   context_notes="", reference_docs=[], module=""),
            "integration": TaskConfig(id="integration", name="Integration", description="",
                                      category="", estimated_turns=30, priority="P1",
                                      depends_on=["backend", "frontend"], input_files=[],
                                      output_files=[], context_notes="",
                                      reference_docs=[], module=""),
        }
        assert _detect_cycle(tasks) is None
