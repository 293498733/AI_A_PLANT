from pathlib import Path
from pipeline.config import (
    StageConfig, TaskConfig, TaskGraphConfig, PipelineConfig,
    load_pipeline, load_task_graph, load_profile,
)


class TestStageConfig:
    def test_defaults(self):
        s = StageConfig(id="s1", name="Stage 1", state_value="done")
        assert s.recipe == ""
        assert s.max_turns == 0
        assert s.params == {}
        assert s.output_file is None
        assert s.is_checkpoint is False
        assert s.checkpoint_prompt == ""
        assert s.is_task_graph is False

    def test_all_fields(self):
        s = StageConfig(
            id="p3", name="Design", recipe="r.yaml", max_turns=100,
            params={"k": "v"}, output_file="out.md", is_checkpoint=False,
            checkpoint_prompt="", state_value="design_done", is_task_graph=False,
        )
        assert s.id == "p3"
        assert s.max_turns == 100


class TestTaskConfig:
    def test_defaults(self):
        t = TaskConfig(id="t1", name="Task", description="Desc")
        assert t.category == ""
        assert t.estimated_turns == 40
        assert t.priority == "P1"
        assert t.depends_on == []
        assert t.input_files == []
        assert t.output_files == []
        assert t.context_notes == ""
        assert t.reference_docs == []
        assert t.module == ""
        assert t.parallel_group is None
        assert t.retry_limit == 2
        assert t.timeout_minutes == 15

    def test_all_fields(self):
        t = TaskConfig(
            id="t2", name="API", description="Build API",
            category="backend", estimated_turns=60, priority="P0",
            depends_on=["t1"], input_files=["README.md"],
            output_files=["api.py"], context_notes="Use FastAPI",
            reference_docs=["03-plan.md"], module="backend",
            parallel_group="group1", retry_limit=3, timeout_minutes=30,
        )
        assert t.retry_limit == 3
        assert t.timeout_minutes == 30
        assert t.parallel_group == "group1"


class TestPipelineConfig:
    def test_find_resume_empty_state(self):
        stages = [StageConfig(id="s1", name="S1", state_value="s1_done")]
        cfg = PipelineConfig(stages=stages)
        assert cfg.find_resume_index("") == 0

    def test_find_resume_found(self):
        stages = [
            StageConfig(id="s1", name="S1", state_value="s1_done"),
            StageConfig(id="s2", name="S2", state_value="s2_done"),
        ]
        cfg = PipelineConfig(stages=stages)
        assert cfg.find_resume_index("s1_done") == 1

    def test_find_resume_unknown(self):
        stages = [StageConfig(id="s1", name="S1", state_value="s1_done")]
        cfg = PipelineConfig(stages=stages)
        assert cfg.find_resume_index("bogus") == 0

    def test_find_resume_last_stage(self):
        stages = [
            StageConfig(id="s1", name="S1", state_value="s1_done"),
            StageConfig(id="s2", name="S2", state_value="done"),
        ]
        cfg = PipelineConfig(stages=stages)
        assert cfg.find_resume_index("done") == 2


FIXTURES = Path(__file__).parent / "fixtures"


class TestLoadPipeline:
    def test_valid(self):
        cfg = load_pipeline(FIXTURES / "pipeline_minimal.yaml")
        assert len(cfg.stages) == 3
        assert cfg.stages[0].id == "phase1"
        assert cfg.stages[0].is_checkpoint is False
        assert cfg.stages[1].is_checkpoint is True
        assert cfg.stages[2].is_task_graph is True

    def test_file_not_found(self, tmp_path):
        try:
            load_pipeline(tmp_path / "nope.yaml")
            assert False, "should have raised"
        except FileNotFoundError:
            pass


class TestLoadTaskGraph:
    def test_valid(self):
        graph = load_task_graph(FIXTURES / "tasks_minimal.yaml")
        assert len(graph.tasks) == 3
        assert graph.tasks[0].id == "t1"
        assert graph.tasks[0].priority == "P0"
        assert graph.tasks[1].depends_on == ["t1"]
        assert graph.tasks[1].retry_limit == 3
        assert graph.tasks[1].timeout_minutes == 20
        assert graph.tasks[2].parallel_group == "ui"
        assert graph.total_estimated_turns == 120
        assert graph.max_workers == 3  # default

    def test_custom_max_workers(self, tmp_path):
        yaml_file = tmp_path / "tasks.yaml"
        yaml_file.write_text("""
version: "1.0"
project: "test"
total_estimated_turns: 10
max_workers: 5
tasks:
  - id: t1
    name: "Test"
    description: "Desc"
    estimated_turns: 10
""")
        graph = load_task_graph(yaml_file)
        assert graph.max_workers == 5

    def test_file_not_found(self, tmp_path):
        try:
            load_task_graph(tmp_path / "nope.yaml")
            assert False, "should have raised"
        except FileNotFoundError:
            pass


class TestLoadProfile:
    def test_valid(self):
        profile = load_profile(FIXTURES / "profile_test.yml")
        assert profile["profile"] == "java-spring"
        assert profile["backend"]["language"] == "Java"

    def test_missing_returns_none(self, tmp_path):
        assert load_profile(tmp_path / "nope.yml") is None
