"""Multica Native 执行契约。

这些 dataclass 是 AI Dev Flow 与外部管理层之间的稳定边界。
CLI、Mock Multica、未来真实 Multica 都应组装 RunRequest，并消费
RunEvent / RunResult，而不是直接耦合 argparse 或 .pipeline_stage。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def new_run_id() -> str:
    """生成本地可读的 run id，便于在 .ai-dev/runs 下排查。"""
    ts = time.strftime("%Y%m%d-%H%M%S")
    return f"run-{ts}-{uuid.uuid4().hex[:8]}"


@dataclass(slots=True)
class RunRequest:
    """一次管线运行请求。

    这是 Multica 未来调用执行层的最小输入模型。字段保持接近当前 CLI，
    方便短期兼容；后续可逐步把 requirement_text/artifact_id 等托管字段
    接入真实 Multica。
    """

    project_path: str
    run_id: str = field(default_factory=new_run_id)
    git_url: str = ""
    git_branch: str = ""
    req_file: str = ""
    requirement_text: str = ""
    resume: bool = False
    new_run: bool = False
    from_stage: str = ""
    dry_run: bool = False
    debug: bool = False
    verbose: bool = False
    pull: bool = False
    ci: bool = False
    source: str = "cli"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class StageRecord:
    """阶段执行摘要。"""

    id: str
    name: str
    status: str
    elapsed_seconds: float = 0.0
    message: str = ""


@dataclass(slots=True)
class RunEvent:
    """执行过程事件，供 Multica/Warp 实时消费。"""

    run_id: str
    type: str
    timestamp: float = field(default_factory=time.time)
    payload: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, run_id: str, event_type: str, **payload: Any) -> "RunEvent":
        return cls(run_id=run_id, type=event_type, payload=payload)

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "type": self.type,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }


@dataclass(slots=True)
class RunResult:
    """管线运行最终结果。"""

    run_id: str
    status: str
    exit_code: int = 0
    project_root: Path | None = None
    ai_dev_dir: Path | None = None
    outputs_dir: Path | None = None
    stages: list[StageRecord] = field(default_factory=list)
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and self.status == "completed"
