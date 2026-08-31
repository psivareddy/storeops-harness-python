"""alerts is driven by events, never by a sibling service call.

This is the positive proof for the event-bus-only rule (Failure Mode 4): a notification appears
in the alerts module purely because ``activities`` published an event, with no import in either
direction between the two modules.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.activities.models import TaskStatus
from app.activities.service import ActivitiesService
from app.alerts.models import AlertType, NotificationStatus
from app.shared.errors import NotificationNotFoundError
from app.shared.events import Event, EventName
from tests.conftest import AlertsHarness, api_endpoints


def test_blocking_an_activity_raises_an_escalation_alert_via_the_bus(
    alerts: AlertsHarness,
) -> None:
    """End-to-end across the boundary: activities publishes, alerts reacts, and neither module
    imports the other."""
    activities_on_same_bus = ActivitiesService(bus=alerts.bus)
    before = len(alerts.service.list_notifications())

    activities_on_same_bus.update_status("task-1", TaskStatus.BLOCKED)

    after = alerts.service.list_notifications()
    assert len(after) == before + 1

    raised = alerts.service.notifications_for_task("task-1")
    escalations = [item for item in raised if item.alert_type is AlertType.ESCALATION]
    assert len(escalations) == 1
    assert escalations[0].recipient_id == "user-3"  # the task's assignee
    assert escalations[0].status is NotificationStatus.PENDING
    assert escalations[0].store_id == "store-101"


@pytest.mark.parametrize("target", [TaskStatus.DONE, TaskStatus.IN_PROGRESS])
def test_non_blocking_transitions_raise_no_alert(
    alerts: AlertsHarness, target: TaskStatus
) -> None:
    """The handler must be safe to invoke for every status change, not just the one it cares
    about -- it is subscribed to all of them."""
    activities_on_same_bus = ActivitiesService(bus=alerts.bus)
    before = len(alerts.service.list_notifications())

    activities_on_same_bus.update_status("task-1", target)

    assert len(alerts.service.list_notifications()) == before
    assert len(alerts.bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 1


def test_blocking_an_unassigned_activity_raises_no_alert(alerts: AlertsHarness) -> None:
    """task-5 has no assignee. There is nobody to escalate to, so the handler must decline
    rather than invent a recipient."""
    activities_on_same_bus = ActivitiesService(bus=alerts.bus)
    before = len(alerts.service.list_notifications())

    activities_on_same_bus.update_status("task-5", TaskStatus.BLOCKED)

    assert len(alerts.service.list_notifications()) == before


def _escalations_for(alerts: AlertsHarness, task_id: str) -> int:
    """Escalations only. ``notification-1`` is seeded against task-1, so a raw count for that
    task would be 1 before anything happens."""
    return len(
        [
            item
            for item in alerts.service.notifications_for_task(task_id)
            if item.alert_type is AlertType.ESCALATION
        ]
    )


def test_handler_tolerates_a_payload_with_missing_fields(alerts: AlertsHarness) -> None:
    """Defensive: the bus carries plain mappings, so a malformed payload must not crash the
    publisher's transaction."""
    alerts.service.handle_activity_status_changed(Event(name="ACTIVITY_STATUS_CHANGED", payload={}))

    assert _escalations_for(alerts, "task-1") == 0


def test_registering_handlers_twice_does_not_double_alerts(alerts: AlertsHarness) -> None:
    alerts.service.register_event_handlers(alerts.bus)
    alerts.service.register_event_handlers(alerts.bus)

    ActivitiesService(bus=alerts.bus).update_status("task-1", TaskStatus.BLOCKED)

    assert _escalations_for(alerts, "task-1") == 1


def test_get_notification_raises_typed_error_when_absent(alerts: AlertsHarness) -> None:
    with pytest.raises(NotificationNotFoundError) as caught:
        alerts.service.get_notification("notification-999")

    assert caught.value.code == "NOTIFICATION_NOT_FOUND"
    assert caught.value.status_code == 404


def test_get_notification_returns_the_seeded_alert(alerts: AlertsHarness) -> None:
    assert alerts.service.get_notification("notification-2").alert_type is AlertType.SLA_BREACH


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def test_list_notifications_returns_seeded_alerts(client: TestClient) -> None:
    response = client.get("/api/notifications")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["alert_type"] for item in body} == {"INVENTORY", "SLA_BREACH"}


def test_list_notifications_filters_by_recipient_and_type(client: TestClient) -> None:
    by_recipient = client.get("/api/notifications", params={"recipient_id": "user-2"}).json()
    assert [item["id"] for item in by_recipient] == ["notification-2"]

    by_type = client.get("/api/notifications", params={"alert_type": "INVENTORY"}).json()
    assert [item["id"] for item in by_type] == ["notification-1"]


def test_blocking_a_task_over_http_surfaces_a_new_alert_over_http(client: TestClient) -> None:
    """The full cross-module path through the running application."""
    before = len(client.get("/api/notifications").json())

    client.patch("/api/tasks/task-1/status", json={"status": "BLOCKED"})

    after = client.get("/api/notifications", params={"alert_type": "ESCALATION"}).json()
    assert len(after) == 1
    assert after[0]["subject_task_id"] == "task-1"
    assert len(client.get("/api/notifications").json()) == before + 1


def test_alerts_router_exposes_no_write_endpoint(client: TestClient) -> None:
    """A notification may only come into existence via an event, so there must be no endpoint
    that creates one."""
    endpoints = api_endpoints(client, prefix="/api/notifications")

    assert endpoints == {("GET", "/api/notifications")}


def test_write_verbs_against_the_alerts_endpoint_are_not_routed(client: TestClient) -> None:
    for verb in ("post", "put", "patch", "delete"):
        response = getattr(client, verb)("/api/notifications")
        assert response.status_code == 405, f"{verb.upper()} unexpectedly routed"
