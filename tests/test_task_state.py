from pipeline.task_state import (
    TaskStateManager, STATUS_PENDING, STATUS_READY, STATUS_IN_PROGRESS,
    STATUS_COMPLETED, STATUS_FAILED, STATUS_SKIPPED,
)


class TestTaskStateManagerInit:
    def test_creates_pending_tasks(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2", "t3"], {}, {})
        assert mgr.tasks["t1"]["status"] == STATUS_PENDING
        assert mgr.tasks["t2"]["status"] == STATUS_PENDING
        assert mgr.tasks["t3"]["status"] == STATUS_PENDING
        assert mgr.tasks["t1"]["retries"] == 0
        assert mgr.tasks["t1"]["started_at"] is None

    def test_merges_existing_state(self, temp_ai_dev_dir):
        from pipeline.state import write_task_state
        write_task_state(temp_ai_dev_dir, {
            "t1": {"status": STATUS_COMPLETED, "started_at": None,
                   "completed_at": "2026-01-01", "retries": 0,
                   "commit_hash": "abc", "output_files_produced": ["a.py"],
                   "error_message": None, "notes": None},
        })
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], {}, {})
        assert mgr.tasks["t1"]["status"] == STATUS_COMPLETED
        assert mgr.tasks["t1"]["commit_hash"] == "abc"
        assert mgr.tasks["t2"]["status"] == STATUS_PENDING

    def test_stores_dependencies_and_modules(self, temp_ai_dev_dir):
        deps = {"t1": ["t2"], "t2": []}
        mods = {"t1": "core", "t2": "core"}
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], deps, mods)
        assert mgr.dependencies == deps
        assert mgr.modules == mods


class TestMarkTransitions:
    def test_mark_ready(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_ready("t1")
        assert mgr.tasks["t1"]["status"] == STATUS_READY

    def test_mark_in_progress_sets_timestamp(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_in_progress("t1")
        assert mgr.tasks["t1"]["status"] == STATUS_IN_PROGRESS
        assert mgr.tasks["t1"]["started_at"] is not None

    def test_mark_completed(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_completed("t1", "abc123", ["out.py"])
        t = mgr.tasks["t1"]
        assert t["status"] == STATUS_COMPLETED
        assert t["commit_hash"] == "abc123"
        assert t["output_files_produced"] == ["out.py"]
        assert t["completed_at"] is not None

    def test_mark_failed_increments_retries(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_failed("t1", "something broke")
        assert mgr.tasks["t1"]["status"] == STATUS_FAILED
        assert mgr.tasks["t1"]["error_message"] == "something broke"
        assert mgr.tasks["t1"]["retries"] == 1
        mgr.mark_failed("t1", "broke again")
        assert mgr.tasks["t1"]["retries"] == 2

    def test_mark_skipped(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_skipped("t1", "not needed")
        assert mgr.tasks["t1"]["status"] == STATUS_SKIPPED
        assert mgr.tasks["t1"]["notes"] == "not needed"

    def test_mark_skipped_default_reason(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_skipped("t1")
        assert mgr.tasks["t1"]["notes"] == ""


class TestGetNextReady:
    def test_no_deps_ready_immediately(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        ready = mgr.get_next_ready(set())
        assert "t1" in ready

    def test_dep_not_satisfied(self, temp_ai_dev_dir):
        deps = {"t1": ["t2"]}
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], deps, {})
        ready = mgr.get_next_ready(set())
        assert "t1" not in ready
        assert "t2" in ready

    def test_dep_satisfied(self, temp_ai_dev_dir):
        deps = {"t1": ["t2"]}
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], deps, {})
        ready = mgr.get_next_ready({"t2"})
        assert "t1" in ready

    def test_skipped_counts_as_completed(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], {"t1": ["t2"]}, {})
        mgr.mark_skipped("t2", "reason")
        ready = mgr.get_next_ready({"t2"})
        assert "t1" in ready

    def test_not_pending_skipped(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        mgr.mark_completed("t1", "abc", [])
        ready = mgr.get_next_ready(set())
        assert "t1" not in ready

    def test_multiple_deps_all_needed(self, temp_ai_dev_dir):
        deps = {"t1": ["t2", "t3"]}
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2", "t3"], deps, {})
        ready = mgr.get_next_ready({"t2"})
        assert "t1" not in ready
        ready = mgr.get_next_ready({"t2", "t3"})
        assert "t1" in ready


class TestResetInProgress:
    def test_resets_in_progress_to_pending(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], {}, {})
        mgr.mark_in_progress("t1")
        mgr.mark_completed("t2", "abc", [])
        reset = mgr.reset_in_progress()
        assert "t1" in reset
        assert mgr.tasks["t1"]["status"] == STATUS_PENDING
        assert mgr.tasks["t1"]["started_at"] is None
        assert mgr.tasks["t2"]["status"] == STATUS_COMPLETED

    def test_nothing_to_reset(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        reset = mgr.reset_in_progress()
        assert reset == []


class TestProgress:
    def test_all_pending(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2", "t3"], {}, {})
        done, total, failed = mgr.progress()
        assert done == 0
        assert total == 3
        assert failed == 0

    def test_mixed_statuses(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2", "t3", "t4"], {}, {})
        mgr.mark_completed("t1", "a", [])
        mgr.mark_skipped("t2")
        mgr.mark_failed("t3", "err")
        done, total, failed = mgr.progress()
        assert done == 2
        assert total == 4
        assert failed == 1


class TestModuleProgress:
    def test_per_module_counts(self, temp_ai_dev_dir):
        mods = {"t1": "core", "t2": "core", "t3": "ui"}
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2", "t3"], {}, mods)
        mgr.mark_completed("t1", "a", [])
        mgr.mark_failed("t2", "err")
        prog = mgr.get_module_progress()
        assert prog["core"] == (1, 2, 1)
        assert prog["ui"] == (0, 1, 0)

    def test_unassigned_module(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1"], {}, {})
        prog = mgr.get_module_progress()
        assert prog["_unassigned"] == (0, 1, 0)


class TestSave:
    def test_save_persists_to_file(self, temp_ai_dev_dir):
        mgr = TaskStateManager(temp_ai_dev_dir, ["t1", "t2"], {}, {})
        mgr.mark_completed("t1", "abc", ["x.py"])
        mgr.save()
        state_file = temp_ai_dev_dir / "task_state.json"
        assert state_file.exists()
        import json
        data = json.loads(state_file.read_text(encoding="utf-8"))
        assert data["t1"]["status"] == STATUS_COMPLETED
        assert data["t2"]["status"] == STATUS_PENDING
