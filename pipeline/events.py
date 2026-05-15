"""事件输出适配器。

当前先提供本地 JSONL 事件流，作为 Multica 未完成前的可替换管理层。
真实 Multica 接入时只需要实现同样的 EventSink 接口。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from pipeline.contracts import RunEvent

logger = logging.getLogger("ai-dev-flow")


class EventSink(Protocol):
    """运行事件消费者。"""

    def emit(self, event: RunEvent) -> None:
        ...


class NullEventSink:
    """默认事件消费者：丢弃事件，保持现有 CLI 行为。"""

    def emit(self, event: RunEvent) -> None:
        return None


class JsonlEventSink:
    """将事件追加写入 JSON Lines 文件。"""

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def emit(self, event: RunEvent) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("failed to write run event: %s", event.type)


class TeeEventSink:
    """把事件扇出给多个 sink。"""

    def __init__(self, *sinks: EventSink):
        self.sinks = [sink for sink in sinks if sink is not None]

    def emit(self, event: RunEvent) -> None:
        for sink in self.sinks:
            sink.emit(event)
