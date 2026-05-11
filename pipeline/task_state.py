"""任务状态管理 — task_state.json 的读写与依赖拓扑。"""

import logging
from pathlib import Path
from pipeline.state import read_task_state as _read, write_task_state as _write

logger = logging.getLogger("ai-dev-flow")

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


class TaskStateManager:
    """管理 .ai-dev/task_state.json 中的任务执行状态。"""

    def __init__(self, ai_dev_dir: Path, task_ids: list[str]):
        self.state_file = ai_dev_dir / "task_state.json"
        self.tasks: dict[str, dict] = {}
        existing = _read(ai_dev_dir) or {}
        for tid in task_ids:
            if tid in existing:
                self.tasks[tid] = existing[tid]
            else:
                self.tasks[tid] = {
                    "status": STATUS_PENDING,
                    "started_at": None,
                    "completed_at": None,
                    "retries": 0,
                    "commit_hash": None,
                    "output_files_produced": [],
                    "error_message": None,
                    "notes": None,
                }

    def save(self) -> None:
        _write(self.state_file.parent, self.tasks)

    def get(self, task_id: str) -> dict:
        return self.tasks[task_id]

    def mark_ready(self, task_id: str) -> None:
        self.tasks[task_id]["status"] = STATUS_READY

    def mark_in_progress(self, task_id: str) -> None:
        from datetime import datetime
        self.tasks[task_id]["status"] = STATUS_IN_PROGRESS
        self.tasks[task_id]["started_at"] = datetime.now().isoformat()

    def mark_completed(self, task_id: str, commit_hash: str, output_files: list[str]) -> None:
        from datetime import datetime
        t = self.tasks[task_id]
        t["status"] = STATUS_COMPLETED
        t["completed_at"] = datetime.now().isoformat()
        t["commit_hash"] = commit_hash
        t["output_files_produced"] = output_files

    def mark_failed(self, task_id: str, error: str) -> None:
        t = self.tasks[task_id]
        t["status"] = STATUS_FAILED
        t["error_message"] = error
        t["retries"] += 1

    def mark_skipped(self, task_id: str, reason: str = "") -> None:
        t = self.tasks[task_id]
        t["status"] = STATUS_SKIPPED
        t["notes"] = reason

    def get_next_ready(self, completed_ids: set[str]) -> list[str]:
        """返回所有 depends_on 已满足且状态为 pending 的任务 ID。"""
        ready = []
        for tid, tr in self.tasks.items():
            if tr["status"] != STATUS_PENDING:
                continue
            # Check dependencies — external info from TaskConfig
            ready.append(tid)  # Will be filtered by caller using TaskConfig.depends_on
        return ready

    def reset_in_progress(self) -> list[str]:
        """将崩溃残留的 in_progress 任务重置为 pending。返回被重置的任务 ID 列表。"""
        reset = []
        for tid, tr in self.tasks.items():
            if tr["status"] == STATUS_IN_PROGRESS:
                tr["status"] = STATUS_PENDING
                tr["started_at"] = None
                reset.append(tid)
                logger.warning(f"Task {tid} was in_progress during crash — reset to pending")
        return reset

    def progress(self) -> tuple[int, int, int]:
        """返回 (done, total, failed)。"""
        done = sum(1 for t in self.tasks.values()
                   if t["status"] in (STATUS_COMPLETED, STATUS_SKIPPED))
        failed = sum(1 for t in self.tasks.values()
                     if t["status"] == STATUS_FAILED)
        return done, len(self.tasks), failed
