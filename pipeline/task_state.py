"""任务状态管理 — task_state.json 的读写与依赖拓扑。"""

import logging
from pathlib import Path
from pipeline.state import read_task_state as _read, write_task_state as _write

logger = logging.getLogger("ai-dev-flow")

STATUS_PENDING = "pending"
STATUS_READY = "ready"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CODE_PRODUCED = "code_produced"      # goose 成功 + 产出存在 + 验证失败（代码已写入）
STATUS_FAILED_NO_OUTPUT = "failed_no_output"  # goose 失败 或 产出文件不存在
STATUS_FAILED = "failed"
STATUS_SKIPPED = "skipped"


class TaskStateManager:
    """管理 .ai-dev/task_state.json 中的任务执行状态。"""

    def __init__(self, ai_dev_dir: Path, task_ids: list[str],
                 dependencies: dict[str, list[str]] | None = None,
                 modules: dict[str, str] | None = None):
        self.state_file = ai_dev_dir / "task_state.json"
        self.dependencies = dependencies or {}
        self.modules = modules or {}  # task_id -> module_name
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

    def mark_code_produced(
        self, task_id: str, output_files: list[str],
        verification_error: str = "", commit_hash: str = "",
    ) -> None:
        """标记代码已产出但验证失败。状态不同于 failed_no_output。"""
        from datetime import datetime
        t = self.tasks[task_id]
        t["status"] = STATUS_CODE_PRODUCED
        t["completed_at"] = datetime.now().isoformat()
        t["output_files_produced"] = output_files
        t["commit_hash"] = commit_hash
        t["error_message"] = verification_error
        t["retries"] += 1

    def mark_failed_no_output(self, task_id: str, error: str) -> None:
        """标记 goose 未产出有效文件（真正的失败）。"""
        t = self.tasks[task_id]
        t["status"] = STATUS_FAILED_NO_OUTPUT
        t["error_message"] = error
        t["retries"] += 1

    def mark_skipped(self, task_id: str, reason: str = "") -> None:
        t = self.tasks[task_id]
        t["status"] = STATUS_SKIPPED
        t["notes"] = reason

    def get_next_ready(self, completed_ids: set[str]) -> list[str]:
        """返回所有 depends_on 已满足且状态为 pending 的任务 ID。

        code_produced 视为完成：上游代码已产出，下游不应被阻塞。
        """
        ready = []
        for tid, tr in self.tasks.items():
            if tr["status"] != STATUS_PENDING:
                continue
            deps = self.dependencies.get(tid, [])
            if not all(dep in completed_ids for dep in deps):
                continue
            ready.append(tid)
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
        """返回 (done, total, failed)。

        code_produced 计入 done（代码已存在，只是验证未通过）。
        failed_no_output 计入 failed（真正的失败）。
        """
        done = sum(1 for t in self.tasks.values()
                   if t["status"] in (STATUS_COMPLETED, STATUS_SKIPPED, STATUS_CODE_PRODUCED))
        failed = sum(1 for t in self.tasks.values()
                     if t["status"] in (STATUS_FAILED, STATUS_FAILED_NO_OUTPUT))
        return done, len(self.tasks), failed

    def get_module_progress(self) -> dict[str, tuple[int, int, int]]:
        """返回每个模块的 (done, total, failed) 进度映射。"""
        modules: dict[str, dict] = {}
        for tid, ts in self.tasks.items():
            mod = self.modules.get(tid, "_unassigned")
            if mod not in modules:
                modules[mod] = {"done": 0, "total": 0, "failed": 0}
            modules[mod]["total"] += 1
            if ts["status"] in (STATUS_COMPLETED, STATUS_SKIPPED, STATUS_CODE_PRODUCED):
                modules[mod]["done"] += 1
            elif ts["status"] in (STATUS_FAILED, STATUS_FAILED_NO_OUTPUT):
                modules[mod]["failed"] += 1
        return {m: (s["done"], s["total"], s["failed"]) for m, s in modules.items()}
