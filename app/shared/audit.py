"""In-memory audit sink — records every domain event for governance.

The sink subscribes to the event bus rather than being called by services. That inversion is the
point: a service cannot forget to write an audit entry, because publishing the event *is* the
audit entry. It also means the audit trail cannot be bypassed by a direct sibling-repository
write, since such a write raises no event and therefore shows up as a missing entry.

This is shared infrastructure, **not** a sixth business module: it owns no routes, no entities,
and no domain rules, and it never imports a business module.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.shared.events import Event, EventBus, EventName
from app.shared.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One recorded domain event."""

    event_name: str
    payload: Mapping[str, Any]
    recorded_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class AuditSink:
    """Append-only in-memory audit log."""

    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []

    def record(self, event: Event) -> None:
        """Event bus handler. One entry per published event."""
        self._entries.append(AuditEntry(event_name=event.name, payload=event.payload))
        logger.debug("Audit entry recorded for %s", event.name)

    def attach(self, bus: EventBus, event_names: Iterable[str] | None = None) -> None:
        """Subscribe to ``event_names``, or to the whole catalogue when omitted."""
        names = tuple(event_names) if event_names is not None else tuple(EventName)
        bus.subscribe_many(names, self.record)

    @property
    def entries(self) -> Sequence[AuditEntry]:
        return tuple(self._entries)

    def entries_for(self, event_name: str) -> Sequence[AuditEntry]:
        """Every entry recorded for ``event_name``, in recording order."""
        return tuple(entry for entry in self._entries if entry.event_name == event_name)

    def count_for(self, event_name: str) -> int:
        """Entry count for ``event_name``. The assertion the harness requires per updated task."""
        return len(self.entries_for(event_name))

    def clear(self) -> None:
        """Drop all entries. Test helper."""
        self._entries.clear()


audit_sink = AuditSink()
"""Process-wide audit sink, attached to the bus by the application factory."""
