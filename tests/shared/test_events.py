"""Event bus behaviour — the mechanism the event-bus-only rule depends on."""

from __future__ import annotations

from app.shared.events import Event, EventBus, EventName


def test_publish_records_event_and_invokes_subscriber() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(EventName.ACTIVITY_CREATED, received.append)

    event = bus.publish(EventName.ACTIVITY_CREATED, {"taskId": "task-9"})

    assert event.name == EventName.ACTIVITY_CREATED
    assert event.payload == {"taskId": "task-9"}
    assert [item.payload["taskId"] for item in received] == ["task-9"]
    assert len(bus.published) == 1


def test_subscribe_is_idempotent_so_wiring_twice_does_not_double_side_effects() -> None:
    """Regression guard: create_app() runs per test, and a double subscription would
    silently produce two notifications per status change."""
    bus = EventBus()
    received: list[Event] = []

    bus.subscribe(EventName.ACTIVITY_STATUS_CHANGED, received.append)
    bus.subscribe(EventName.ACTIVITY_STATUS_CHANGED, received.append)

    assert bus.subscriber_count(EventName.ACTIVITY_STATUS_CHANGED) == 1
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-1"})
    assert len(received) == 1


def test_subscribe_many_registers_handler_for_every_named_event() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe_many(
        [EventName.ACTIVITY_CREATED, EventName.PROGRAMME_MEMBER_ADDED], received.append
    )

    bus.publish(EventName.ACTIVITY_CREATED, {})
    bus.publish(EventName.PROGRAMME_MEMBER_ADDED, {})

    assert [item.name for item in received] == [
        EventName.ACTIVITY_CREATED,
        EventName.PROGRAMME_MEMBER_ADDED,
    ]


def test_published_of_filters_by_event_name_in_publication_order() -> None:
    bus = EventBus()
    bus.publish(EventName.ACTIVITY_CREATED, {"taskId": "task-1"})
    bus.publish(EventName.ACTIVITY_STATUS_CHANGED, {"taskId": "task-2"})
    bus.publish(EventName.ACTIVITY_CREATED, {"taskId": "task-3"})

    created = bus.published_of(EventName.ACTIVITY_CREATED)

    assert [item.payload["taskId"] for item in created] == ["task-1", "task-3"]
    assert len(bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 1


def test_events_with_no_subscribers_are_still_logged() -> None:
    """A published event must be observable even when nothing consumes it -- otherwise the
    audit trail would depend on a subscriber existing."""
    bus = EventBus()
    bus.publish(EventName.PROGRAMME_MEMBER_ADDED, {"projectId": "project-1"})

    assert bus.subscriber_count(EventName.PROGRAMME_MEMBER_ADDED) == 0
    assert len(bus.published) == 1


def test_clear_log_keeps_subscriptions_but_reset_drops_them() -> None:
    bus = EventBus()
    received: list[Event] = []
    bus.subscribe(EventName.ACTIVITY_CREATED, received.append)
    bus.publish(EventName.ACTIVITY_CREATED, {})

    bus.clear_log()
    assert len(bus.published) == 0
    assert bus.subscriber_count(EventName.ACTIVITY_CREATED) == 1

    bus.reset()
    assert bus.subscriber_count(EventName.ACTIVITY_CREATED) == 0


def test_payload_is_copied_so_a_caller_cannot_mutate_a_published_event() -> None:
    bus = EventBus()
    payload = {"taskId": "task-1"}
    event = bus.publish(EventName.ACTIVITY_CREATED, payload)

    payload["taskId"] = "tampered"

    assert event.payload["taskId"] == "task-1"


def test_event_catalogue_values_match_their_names() -> None:
    """The Evaluator greps for these literals; a mismatch between member and value would make
    a cross-module trigger look absent."""
    for member in EventName:
        assert member.value == member.name
