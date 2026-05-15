#!/usr/bin/env python3
"""本地 Multica Native 模拟入口。

真实 Multica 尚未完成前，可以用这个入口以 JSON RunRequest 方式调用
AI Dev Flow 执行内核。事件和结果会落到目标项目:

  .ai-dev/runs/<run_id>/events.jsonl
  .ai-dev/runs/<run_id>/request.json
  .ai-dev/runs/<run_id>/result.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, fields
from pathlib import Path

from pipeline.contracts import RunRequest
from pipeline.runner import PipelineRunner


def _load_request(path: str | None) -> RunRequest:
    if path:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    else:
        data = json.loads(sys.stdin.read())

    allowed = {f.name for f in fields(RunRequest)}
    payload = {k: v for k, v in data.items() if k in allowed}
    payload.setdefault("source", "mock_multica")
    return RunRequest(**payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Dev Flow mock Multica agent")
    parser.add_argument("--request", "-r", help="RunRequest JSON 文件；留空则从 stdin 读取")
    args = parser.parse_args(argv)

    request = _load_request(args.request)
    result = PipelineRunner().run(request)
    data = asdict(result)
    for key in ("project_root", "ai_dev_dir", "outputs_dir"):
        if data.get(key) is not None:
            data[key] = str(data[key])
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
