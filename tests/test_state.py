from pathlib import Path
from pipeline.state import (
    read_stage, write_stage, clear_stage,
    read_note, write_note, clear_note,
    read_task_state, write_task_state,
)


class TestStageFile:
    def test_read_write_roundtrip(self, temp_ai_dev_dir):
        write_stage(temp_ai_dev_dir, "phase2_done")
        assert read_stage(temp_ai_dev_dir) == "phase2_done"

    def test_read_missing_returns_none(self, temp_ai_dev_dir):
        assert read_stage(temp_ai_dev_dir) is None

    def test_clear_removes_file(self, temp_ai_dev_dir):
        write_stage(temp_ai_dev_dir, "done")
        clear_stage(temp_ai_dev_dir)
        assert read_stage(temp_ai_dev_dir) is None


class TestNoteFile:
    def test_read_write_roundtrip(self, temp_ai_dev_dir):
        write_note(temp_ai_dev_dir, "Need to fix auth")
        assert read_note(temp_ai_dev_dir) == "Need to fix auth"

    def test_read_missing_returns_none(self, temp_ai_dev_dir):
        assert read_note(temp_ai_dev_dir) is None

    def test_clear_removes_file(self, temp_ai_dev_dir):
        write_note(temp_ai_dev_dir, "todo")
        clear_note(temp_ai_dev_dir)
        assert read_note(temp_ai_dev_dir) is None


class TestTaskStateFile:
    def test_read_write_roundtrip(self, temp_ai_dev_dir):
        data = {"t1": {"status": "completed", "retries": 0}}
        write_task_state(temp_ai_dev_dir, data)
        result = read_task_state(temp_ai_dev_dir)
        assert result == data

    def test_read_missing_returns_none(self, temp_ai_dev_dir):
        assert read_task_state(temp_ai_dev_dir) is None

    def test_atomic_write_no_tmp_leftover(self, temp_ai_dev_dir):
        write_task_state(temp_ai_dev_dir, {"t1": {"status": "pending"}})
        tmps = list(temp_ai_dev_dir.glob(".task_state_tmp*"))
        assert len(tmps) == 0

    def test_overwrite_preserves_correctness(self, temp_ai_dev_dir):
        write_task_state(temp_ai_dev_dir, {"t1": {"status": "pending"}})
        write_task_state(temp_ai_dev_dir, {"t2": {"status": "completed"}})
        result = read_task_state(temp_ai_dev_dir)
        assert "t2" in result
        assert "t1" not in result
