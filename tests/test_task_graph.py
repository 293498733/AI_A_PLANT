import threading
from pathlib import Path
from pipeline.task_graph import (
    _detect_cycle, _module_bar, _detect_residual_files, _write_context_file,
    _execute_single_task, _TASK_OK, _TASK_RETRY, _TASK_SKIP, _TASK_ABORT,
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


class TestExecuteSingleTask:
    """测试 _execute_single_task 函数（worker 线程核心）。"""

    def _make_task(self, **kw):
        defaults = dict(
            id="t1", name="Test", description="Desc", category="test",
            estimated_turns=10, priority="P0", depends_on=[], input_files=[],
            output_files=["out.py"], context_notes="", reference_docs=[],
            module="core", parallel_group=None, retry_limit=2,
            timeout_minutes=5, sandbox_enabled=True,
        )
        defaults.update(kw)
        return TaskConfig(**defaults)

    def _make_mocks(self, mocker, tmp_path):
        """创建 _execute_single_task 所需的全部 mock 对象。"""
        state_mgr = mocker.MagicMock()
        state_mgr.tasks = {"t1": {"retries": 0, "status": "pending"}}
        context_asm = mocker.MagicMock()
        context_asm.assemble.return_value = mocker.MagicMock(context_notes="ctx")
        context_asm.render_prompt.return_value = "# prompt"
        knowledge_mgr = mocker.MagicMock()
        knowledge_mgr.query.return_value = []
        snapshot_mgr = mocker.MagicMock()
        git = mocker.MagicMock()
        lock = threading.Lock()

        # Mock run_task to return success
        mock_result = mocker.MagicMock()
        mock_result.returncode = 0
        mock_result.stderr = ""
        mocker.patch("pipeline.task_graph.run_task", return_value=mock_result)

        # Mock handle_task_error to return RETRY on first failure
        mocker.patch("pipeline.task_graph.handle_task_error", return_value=mocker.MagicMock())

        # Mock SandboxManager
        mock_sandbox = mocker.MagicMock()
        mock_sandbox.create.return_value = tmp_path
        mock_sandbox.detect_extra_modifications.return_value = set()
        mock_sandbox.sync_outputs.return_value = ["out.py"]
        mocker.patch("pipeline.task_graph.SandboxManager", return_value=mock_sandbox)

        return dict(
            state_mgr=state_mgr, context_asm=context_asm,
            knowledge_mgr=knowledge_mgr, snapshot_mgr=snapshot_mgr,
            git=git, lock=lock, mock_sandbox=mock_sandbox,
        )

    def test_success_path(self, mocker, tmp_path):
        mocks = self._make_mocks(mocker, tmp_path)
        task = self._make_task()
        # 创建产出文件（模拟 goose 生成）
        (tmp_path / "out.py").write_text("# generated")

        result = _execute_single_task(
            tid="t1", task=task,
            state_mgr=mocks["state_mgr"],
            context_asm=mocks["context_asm"],
            knowledge_mgr=mocks["knowledge_mgr"],
            snapshot_mgr=mocks["snapshot_mgr"],
            git=mocks["git"], git_available=True,
            project_root=tmp_path, ai_dev_dir=tmp_path,
            profile_path=tmp_path / "profile.yml",
            task_recipe="recipe.yaml",
            lock=mocks["lock"],
        )

        assert result == _TASK_OK
        mocks["state_mgr"].mark_completed.assert_called_once()
        mocks["snapshot_mgr"].update_snapshot.assert_called_once()

    def test_failure_with_retry(self, mocker, tmp_path):
        mocks = self._make_mocks(mocker, tmp_path)
        task = self._make_task()

        # Override run_task to return failure
        mock_result = mocker.MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "something went wrong"
        mocker.patch("pipeline.task_graph.run_task", return_value=mock_result)

        # handle_task_error returns RETRY_TASK
        from pipeline.error_handler import TaskAction
        mocker.patch("pipeline.task_graph.handle_task_error", return_value=TaskAction.RETRY_TASK)

        result = _execute_single_task(
            tid="t1", task=task,
            state_mgr=mocks["state_mgr"],
            context_asm=mocks["context_asm"],
            knowledge_mgr=mocks["knowledge_mgr"],
            snapshot_mgr=mocks["snapshot_mgr"],
            git=mocks["git"], git_available=True,
            project_root=tmp_path, ai_dev_dir=tmp_path,
            profile_path=tmp_path / "profile.yml",
            task_recipe="recipe.yaml",
            lock=mocks["lock"],
        )

        assert result == _TASK_RETRY
        mocks["state_mgr"].mark_failed.assert_called_once()

    def test_missing_output_files(self, mocker, tmp_path):
        mocks = self._make_mocks(mocker, tmp_path)
        # Output file that doesn't exist
        task = self._make_task(output_files=["nonexistent.py"])

        result = _execute_single_task(
            tid="t1", task=task,
            state_mgr=mocks["state_mgr"],
            context_asm=mocks["context_asm"],
            knowledge_mgr=mocks["knowledge_mgr"],
            snapshot_mgr=mocks["snapshot_mgr"],
            git=mocks["git"], git_available=True,
            project_root=tmp_path, ai_dev_dir=tmp_path,
            profile_path=tmp_path / "profile.yml",
            task_recipe="recipe.yaml",
            lock=mocks["lock"],
        )

        assert result == _TASK_OK  # still OK, just warns about missing

    def test_sandbox_disabled(self, mocker, tmp_path):
        mocks = self._make_mocks(mocker, tmp_path)
        task = self._make_task(sandbox_enabled=False)

        result = _execute_single_task(
            tid="t1", task=task,
            state_mgr=mocks["state_mgr"],
            context_asm=mocks["context_asm"],
            knowledge_mgr=mocks["knowledge_mgr"],
            snapshot_mgr=mocks["snapshot_mgr"],
            git=mocks["git"], git_available=True,
            project_root=tmp_path, ai_dev_dir=tmp_path,
            profile_path=tmp_path / "profile.yml",
            task_recipe="recipe.yaml",
            lock=mocks["lock"],
        )

        assert result == _TASK_OK
        # SandboxManager.create should not be called when sandbox disabled
        mocks["mock_sandbox"].create.assert_not_called()
