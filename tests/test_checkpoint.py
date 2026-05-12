from pipeline.checkpoint import confirm, preview, ask_boolean, set_ci_mode
from pipeline.error_handler import (
    handle_error, handle_task_error, Action, TaskAction, set_ci_mode as set_error_ci,
)
from pathlib import Path


class TestCheckpointCiMode:
    def test_confirm_does_not_block(self, ci_mode, capsys):
        confirm("Test Title", "Test prompt")
        captured = capsys.readouterr()
        assert "[CI]" in captured.out
        assert "Test Title" in captured.out

    def test_confirm_with_preview_file(self, ci_mode, capsys, tmp_path):
        f = tmp_path / "test.md"
        f.write_text("line 1\nline 2\n", encoding="utf-8")
        confirm("Title", "Prompt", f)
        captured = capsys.readouterr()
        assert "[CI]" in captured.out

    def test_preview_shows_content(self, capsys, tmp_path):
        f = tmp_path / "preview.md"
        f.write_text("\n".join(f"line {i}" for i in range(30)), encoding="utf-8")
        preview(f, lines=25)
        captured = capsys.readouterr()
        assert "line 0" in captured.out
        assert "line 24" in captured.out
        assert "省略" in captured.out

    def test_preview_missing_file(self, capsys, tmp_path):
        preview(tmp_path / "nope.md")
        captured = capsys.readouterr()
        assert "无法预览" in captured.out

    def test_ask_boolean_ci_true(self, ci_mode, capsys):
        assert ask_boolean("Proceed?", default=True) is True
        captured = capsys.readouterr()
        assert "[CI]" in captured.out

    def test_ask_boolean_ci_false_default(self, ci_mode, capsys):
        assert ask_boolean("Proceed?", default=False) is False
        captured = capsys.readouterr()
        assert "N" in captured.out


class TestErrorHandlerCiMode:
    def test_handle_error_returns_skip(self, ci_mode, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        assert handle_error(ad) == Action.SKIP

    def test_handle_task_error_with_retries(self, ci_mode, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        assert handle_task_error("t1", "Task", 1, 3, ad) == TaskAction.RETRY_TASK

    def test_handle_task_error_retries_exhausted(self, ci_mode, tmp_path):
        ad = tmp_path / ".ai-dev"
        ad.mkdir()
        assert handle_task_error("t1", "Task", 3, 3, ad) == TaskAction.SKIP_TASK


class TestActionEnums:
    def test_action_values(self):
        assert Action.RETRY.value == "retry"
        assert Action.FIX.value == "fix"
        assert Action.NOTE_EXIT.value == "note_exit"
        assert Action.SKIP.value == "skip"

    def test_task_action_values(self):
        assert TaskAction.RETRY_TASK.value == "retry_task"
        assert TaskAction.SKIP_TASK.value == "skip_task"
        assert TaskAction.ABORT_GRAPH.value == "abort_graph"
        assert TaskAction.NOTE_EXIT.value == "note_exit"
