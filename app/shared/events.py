"""In-process event bus — the only permitted channel for cross-module side effects.

Prevents **Failure Mode 4** — state changes written directly to sibling module repositories.
A direct write bypasses both the audit sink and any other subscriber, so the side effect becomes
invisible to operations; publishing instead keeps the fan-out observable and lets a new consumer
be added without touching the producer.

Payloads are plain mappings, never domain models. That is deliberate: ``app.shared`` may not
import a business module (see ``.importlinter``), so the bus stays ignorant of the domains it
decouples.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from app.shared.logging import get_logger

logger = get_logger(__name__)


class EventName(StrEnum):
    """The StoreOps domain event catalogue.

    Held here rather than in a business module so every producer and consumer resolves the same
    literal, and so the Evaluator has one place to check that a cross-module trigger was raised
    as an event rather than as a direct call.
    """

    ACTIVITY_CREATED = "ACTIVITY_CREATED"
    ACTIVITY_STATUS_CHANGED = "ACTIVITY_STATUS_CHANGED"
    PROGRAMME_MEMBER_ADDED = "PROGRAMME_MEMBER_ADDED"


@dataclass(frozen=True, slots=True)
class Event:
    """An immutable record of something that happened in a business module."""

    name: str
    payload: Mapping[str, Any]
    published_at: datetime = field(default_factory=lambda: datetime.now(UTC))


EventHandler = Callable[[Event], None]


class EventBus:
    """Synchronous publish/subscribe bus with an in-memory publication log.

    The publication log exists so tests and the Evaluator can assert *how many* events a
    business operation raised. Asserting the count is what distinguishes a real check from
    "the endpoint returned 200" (Failure Mode 3).
    """

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._published: list[Event] = []

    def subscribe(self, event_name: str, handler: EventHandler) -> None:
        """Register ``handler`` for ``event_name``.

        Idempotent: re-registering the same handler is a no-op. Without this guard, calling the
        application factory twice in one test session would double every subscription and
        produce two notifications per status change -- a duplicate-side-effect bug that is
        painful to trace back to the wiring.
        """
        handlers = self._handlers[event_name]
        if handler in handlers:
            logger.debug("Handler already subscribed to %s; ignoring", event_name)
            return
        handlers.append(handler)

    def subscribe_many(self, event_names: Iterable[str], handler: EventHandler) -> None:
        for event_name in event_names:
            self.subscribe(event_name, handler)

    def publish(self, event_name: str, payload: Mapping[str, Any]) -> Event:
        """Publish an event and invoke every subscriber synchronously."""
        event = Event(name=event_name, payload=dict(payload))
        self._published.append(event)
        for handler in tuple(self._handlers[event_name]):
            handler(event)
        return event

    @property
    def published(self) -> Sequence[Event]:
        return tuple(self._published)

    def published_of(self, event_name: str) -> Sequence[Event]:
        """Every published event with ``event_name``, in publication order."""
        return tuple(event for event in self._published if event.name == event_name)

    def subscriber_count(self, event_name: str) -> int:
        return len(self._handlers[event_name])

    def clear_log(self) -> None:
        """Drop the publication log, keeping subscriptions intact."""
        self._published.clear()

    def reset(self) -> None:
        """Drop subscriptions and the publication log. Test helper."""
        self._handlers.clear()
        self._published.clear()


event_bus = EventBus()
"""Process-wide bus instance. Services accept an override for isolated unit tests."""
