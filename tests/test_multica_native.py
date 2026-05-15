import argparse
import json
import shutil
import uuid
from pathlib import Path

from pipeline.contracts import RunEvent, RunRequest, RunResult
from pipeline.events import JsonlEventSink
from pipeline.runner import PipelineRunner, request_from_args
from pipeline.stores import LocalRunStore


class ListEventSink:
    def __init__(self):
        self.events = []

    def emit(self, event):
        self.events.append(event)


def _local_tmp_dir(name: str) -> Path:
    path = Path(".pytest-local") / f"{name}-{uuid.uuid4().hex[:8]}"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _cleanup_local_tmp(path: Path) -> None:
    shutil.rmtree(path, ignore_errors=True)
    try:
        path.parent.rmdir()
    except OSError:
        pass


def test_request_from_args_maps_cli_fields():
    args = argparse.Namespace(
        project="D:/work/app",
        git_url="",
        git_branch="main",
        req="需求.md",
        resume=False,
        new_run=True,
        from_stage="phase1",
        dry_run=True,
        debug=True,
        verbose=False,
        pull=True,
        ci=True,
    )

    request = request_from_args(args)

    assert request.project_path == "D:/work/app"
    assert request.req_file == "需求.md"
    assert request.from_stage == "phase1"
    assert request.new_run is True
    assert request.ci is True


def test_pipeline_runner_returns_result_instead_of_exiting_for_missing_project():
    sink = ListEventSink()
    request = RunRequest(project_path="", ci=True, source="test")

    result = PipelineRunner(
        event_sink=sink, persist_local_events=False
    ).run(request)

    assert result.status == "failed"
    assert result.exit_code == 1
    assert result.message == "CI 模式需要指定 --project"
    assert [e.type for e in sink.events] == ["run.failed"]


def test_jsonl_event_sink_writes_events():
    root = _local_tmp_dir("events")
    try:
        event_path = root / "events.jsonl"
        sink = JsonlEventSink(event_path)

        sink.emit(RunEvent.make("run-1", "stage.started", stage_id="phase1"))

        row = json.loads(event_path.read_text(encoding="utf-8"))
        assert row["run_id"] == "run-1"
        assert row["type"] == "stage.started"
        assert row["payload"]["stage_id"] == "phase1"
    finally:
        _cleanup_local_tmp(root)


def test_local_run_store_writes_request_and_result():
    root = _local_tmp_dir("store")
    try:
        store = LocalRunStore(root / ".ai-dev")
        request = RunRequest(project_path="D:/work/app", run_id="run-test")
        result = RunResult(run_id="run-test", status="completed")

        request_path = store.write_request(request)
        result_path = store.write_result(result)

        assert request_path.exists()
        assert result_path.exists()
        assert json.loads(request_path.read_text(encoding="utf-8"))["run_id"] == "run-test"
        assert json.loads(result_path.read_text(encoding="utf-8"))["status"] == "completed"
    finally:
        _cleanup_local_tmp(root)
