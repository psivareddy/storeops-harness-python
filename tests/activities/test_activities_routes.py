"""activities HTTP surface.

Status codes are asserted *alongside* the resulting state, the error code, and the side-effect
counts -- never on their own. Asserting status alone is Failure Mode 3 and is a hard-gate
failure under HG-3.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.shared.audit import audit_sink
from app.shared.events import EventName, event_bus


def test_list_tasks_returns_seeded_activities(client: TestClient) -> None:
    response = client.get("/api/tasks")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 5
    assert {task["id"] for task in body} == {"task-1", "task-2", "task-3", "task-4", "task-5"}
    assert body[0]["status"] == "TODO"


def test_list_tasks_honours_store_and_status_filters(client: TestClient) -> None:
    by_store = client.get("/api/tasks", params={"store_id": "store-102"}).json()
    assert {task["store_id"] for task in by_store} == {"store-102"}

    by_status = client.get("/api/tasks", params={"status": "BLOCKED"}).json()
    assert [task["id"] for task in by_status] == ["task-3"]


def test_get_task_returns_the_addressed_activity(client: TestClient) -> None:
    response = client.get("/api/tasks/task-3")

    assert response.status_code == 200
    assert response.json()["category"] == "COMPLIANCE"
    assert response.json()["priority"] == "CRITICAL"


def test_get_unknown_task_returns_the_typed_error_envelope(client: TestClient) -> None:
    response = client.get("/api/tasks/task-999")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "TASK_NOT_FOUND"
    assert error["statusCode"] == 404
    assert error["details"] == {"taskId": "task-999"}


def test_patch_status_updates_state_publishes_one_event_and_audits_once(
    client: TestClient,
) -> None:
    response = client.patch("/api/tasks/task-1/status", json={"status": "DONE"})

    # status AND resulting state
    assert response.status_code == 200
    assert response.json()["status"] == "DONE"
    assert client.get("/api/tasks/task-1").json()["status"] == "DONE"

    # side effects: exactly one event, exactly one audit entry
    events = event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)
    assert len(events) == 1
    assert events[0].payload["previousStatus"] == "TODO"
    assert audit_sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1


def test_patch_status_rejecting_a_terminal_task_returns_409_and_changes_nothing(
    client: TestClient,
) -> None:
    response = client.patch("/api/tasks/task-4/status", json={"status": "TODO"})

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "INVALID_STATUS_TRANSITION"
    assert error["details"]["currentStatus"] == "DONE"

    # the business outcome that matters: state and side-effect logs are untouched
    assert client.get("/api/tasks/task-4").json()["status"] == "DONE"
    assert len(event_bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 0
    assert audit_sink.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 0


def test_patch_unknown_task_returns_404_and_publishes_nothing(client: TestClient) -> None:
    response = client.patch("/api/tasks/task-999/status", json={"status": "DONE"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "TASK_NOT_FOUND"
    assert len(event_bus.published) == 0


def test_patch_with_an_unknown_status_is_rejected_by_validation(client: TestClient) -> None:
    """Pydantic rejects the enum before the service is reached, so no event is published."""
    response = client.patch("/api/tasks/task-1/status", json={"status": "NOT_A_STATUS"})

    assert response.status_code == 422
    assert client.get("/api/tasks/task-1").json()["status"] == "TODO"
    assert len(event_bus.published) == 0


def test_create_task_returns_201_persists_and_publishes_activity_created(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/tasks",
        json={
            "title": "Verify promotional signage",
            "store_id": "store-101",
            "priority": "HIGH",
            "category": "PLANOGRAM",
        },
    )

    assert response.status_code == 201
    created = response.json()
    assert created["status"] == "TODO"
    assert created["priority"] == "HIGH"

    listed = client.get("/api/tasks").json()
    assert len(listed) == 6
    assert created["id"] in {task["id"] for task in listed}

    assert len(event_bus.published_of(EventName.ACTIVITY_CREATED)) == 1
    assert audit_sink.count_for(EventName.ACTIVITY_CREATED) == 1


def test_create_task_with_blank_title_is_rejected_and_creates_nothing(
    client: TestClient,
) -> None:
    response = client.post("/api/tasks", json={"title": "", "store_id": "store-101"})

    assert response.status_code == 422
    assert len(client.get("/api/tasks").json()) == 5
    assert len(event_bus.published) == 0
