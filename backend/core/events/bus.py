from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, DefaultDict, Type


Handler = Callable[[Any], None]


@dataclass
class EventBus:
    _handlers: DefaultDict[Type, list[Handler]]

    def __init__(self) -> None:
        self._handlers = defaultdict(list)

    def subscribe(self, event_type: Type, handler: Handler) -> None:
        self._handlers[event_type].append(handler)

    def publish(self, event: Any) -> None:
        # best-effort: handlers should not break the caller
        for h in list(self._handlers.get(type(event), [])):
            try:
                h(event)
            except Exception:
                continue


_BUS: EventBus | None = None


def get_event_bus() -> EventBus:
    global _BUS
    if _BUS is None:
        _BUS = EventBus()
    return _BUS

