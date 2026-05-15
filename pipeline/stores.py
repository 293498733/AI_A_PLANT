"""本地运行存储。

Multica Native 的长期形态会由管理层托管状态、事件与产物。当前先用
.ai-dev/runs/<run_id>/ 模拟这层能力，保证执行内核已经按 run 维度组织。
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from pipeline.contracts import RunRequest, RunResult
from pipeline.events import JsonlEventSink


class LocalRunStore:
    """按 run_id 管理本地事件和结果。"""

    def __init__(self, ai_dev_dir: Path):
        self.ai_dev_dir = ai_dev_dir

    def run_dir(self, run_id: str) -> Path:
        return self.ai_dev_dir / "runs" / run_id

    def event_sink(self, run_id: str) -> JsonlEventSink:
        return JsonlEventSink(self.run_dir(run_id) / "events.jsonl")

    def write_request(self, request: RunRequest) -> Path:
        path = self.run_dir(request.run_id) / "request.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = asdict(request)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def write_result(self, result: RunResult) -> Path:
        path = self.run_dir(result.run_id) / "result.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data: dict[str, Any] = asdict(result)
        for key in ("project_root", "ai_dev_dir", "outputs_dir"):
            if data.get(key) is not None:
                data[key] = str(data[key])
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return path
