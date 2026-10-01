"""Small synchronous event bus; handlers execute in the publisher's thread."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable


@dataclass(frozen=True)
class Event:
    name: str
    device_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    timestamp_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


EventHandler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, name: str, handler: EventHandler) -> None:
        self._handlers[name].append(handler)

    def publish(self, event: Event) -> None:
        for handler in tuple(self._handlers[event.name]) + tuple(self._handlers["*"]):
            handler(event)
