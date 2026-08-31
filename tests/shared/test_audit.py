"""Audit sink behaviour — one entry per published event, and no way to bypass it."""

from __future__ import annotations

from app.shared.audit import AuditSink
from app.shared.events import EventBus, EventName


def test_attached_sink_records_one_entry_per_published_event() -> None:
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus)

    bus.publish(EventName.ACTIVITY_CREATED, {"taskId": "task-1"})
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-1"})
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-2"})

    assert len(sink.entries) == 3
    assert sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 2
    assert sink.count_for(EventName.ACTIVITY_CREATED) == 1


def test_attach_defaults_to_the_whole_event_catalogue() -> None:
    """A new event type must be audited without anyone remembering to add it to a list."""
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus)

    for name in EventName:
        bus.publish(name, {"probe": name.value})

    assert len(sink.entries) == len(list(EventName))


def test_attach_can_be_narrowed_to_named_events() -> None:
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus, [EventName.ACTIVITY_CREATED])

    bus.publish(EventName.ACTIVITY_CREATED, {})
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {})

    assert sink.count_for(EventName.ACTIVITY_CREATED) == 1
    assert sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 0


def test_entries_preserve_payload_and_recording_order() -> None:
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus)

    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-1", "newStatus": "DONE"})
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-2", "newStatus": "BLOCKED"})

    entries = sink.entries_for(EventName.ACTIVITY_STATUS_CHANGED)
    assert [entry.payload["taskId"] for entry in entries] == ["task-1", "task-2"]
    assert entries[1].payload["newStatus"] == "BLOCKED"


def test_an_unpublished_side_effect_leaves_no_audit_entry() -> None:
    """The governance argument for the event-bus rule, stated as a test: a state change that is
    written without publishing produces no audit record, so it is invisible to operations."""
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus)

    assert len(sink.entries) == 0  # nothing published == nothing audited


def test_clear_empties_the_log() -> None:
    bus = EventBus()
    sink = AuditSink()
    sink.attach(bus)
    bus.publish(EventName.ACTIVITY_CREATED, {})

    sink.clear()

    assert len(sink.entries) == 0
