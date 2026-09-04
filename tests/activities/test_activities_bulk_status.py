"""Sprint-1 acceptance tests: PATCH /api/activities/bulk-status.

One test per acceptance criterion in ``.harness/output/sprint-1-contract.md``, with the exact
names the contract specifies. Every test asserts resulting state, error code, event count and
audit count as applicable -- never an HTTP status alone (HG-3).

Counts use ``==`` with an exact number, never ``>=``: an implementation that publishes per
*requested* id rather than per *successful* update passes a ``>=`` check and fails these.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.activities.models import TaskStatus
from app.shared.audit import audit_sink
from app.shared.errors import ValidationError
from app.shared.events import EventName, event_bus
from tests.conftest import ActivitiesHarness

BULK_STATUS_PATH = "/api/activities/bulk-status"
STATUS_CHANGED = EventName.ACTIVITY_STATUS_CHANGED


def _status_of(client: TestClient, task_id: str) -> str:
    """Read a task's status back from the API rather than trusting the bulk response body."""
    response = client.get(f"/api/tasks/{task_id}")
    assert response.status_code == 200
    return str(response.json()["status"])


# -- AC-1 -----------------------------------------------------------------------------------
def test_all_success_publishes_one_event_per_task(client: TestClient) -> None:
    """AC-1: every id valid -> all update, HTTP 200, exactly 2 events and 2 audit entries."""
    response = client.patch(
        BULK_STATUS_PATH, json={"task_ids": ["task-1", "task-2"], "status": "DONE"}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["updated"] == 2
    assert body["failed"] == 0
    assert [item["taskId"] for item in body["results"]] == ["task-1", "task-2"]
    assert [item["outcome"] for item in body["results"]] == ["UPDATED", "UPDATED"]
    assert all(item["error"] is None for item in body["results"])

    # 1. resulting state, read back
    assert _status_of(client, "task-1") == "DONE"
    assert _status_of(client, "task-2") == "DONE"

    # 3 + 4. one event and one audit entry per successful update -- exactly 2, not 3
    events = event_bus.published_of(STATUS_CHANGED)
    assert len(events) == 2
    assert [event.payload["taskId"] for event in events] == ["task-1", "task-2"]
    assert [event.payload["previousStatus"] for event in events] == ["TODO", "IN_PROGRESS"]
    assert {event.payload["newStatus"] for event in events} == {"DONE"}
    assert audit_sink.count_for(STATUS_CHANGED) == 2


# -- AC-2 -----------------------------------------------------------------------------------
def test_partial_failure_returns_207_and_updates_only_valid_tasks(client: TestClient) -> None:
    """AC-2: one absent id -> others update, TASK_NOT_FOUND for it, HTTP 207, 2 events."""
    response = client.patch(
        BULK_STATUS_PATH,
        json={"task_ids": ["task-1", "task-999", "task-2"], "status": "DONE"},
    )

    assert response.status_code == 207
    body = response.json()
    assert body["updated"] == 2
    assert body["failed"] == 1

    # request order preserved, so a client can zip results against its own input (A-5)
    assert [item["taskId"] for item in body["results"]] == ["task-1", "task-999", "task-2"]
    assert [item["outcome"] for item in body["results"]] == ["UPDATED", "FAILED", "UPDATED"]

    # 2. the failed item keeps its specific code, not a flattened generic one
    missing = body["results"][1]
    assert missing["error"]["code"] == "TASK_NOT_FOUND"
    assert missing["error"]["statusCode"] == 404
    assert missing["error"]["details"]["taskId"] == "task-999"
    assert missing["status"] is None

    # 1. resulting state, read back
    assert _status_of(client, "task-1") == "DONE"
    assert _status_of(client, "task-2") == "DONE"
    assert client.get("/api/tasks/task-999").status_code == 404

    # 3 + 4. two successes -> exactly two events and two audit entries, not three
    events = event_bus.published_of(STATUS_CHANGED)
    assert len(events) == 2
    assert [event.payload["taskId"] for event in events] == ["task-1", "task-2"]
    assert audit_sink.count_for(STATUS_CHANGED) == 2


# -- AC-3 -----------------------------------------------------------------------------------
def test_done_task_in_batch_yields_invalid_status_transition_and_no_event(
    client: TestClient,
) -> None:
    """AC-3: the transition rule still applies in bulk -- task-4 is DONE and terminal."""
    before = client.get("/api/tasks/task-4").json()["updated_at"]

    response = client.patch(
        BULK_STATUS_PATH, json={"task_ids": ["task-1", "task-4"], "status": "DONE"}
    )

    assert response.status_code == 207
    body = response.json()
    assert body["updated"] == 1
    assert body["failed"] == 1
    assert [item["outcome"] for item in body["results"]] == ["UPDATED", "FAILED"]

    # 2. error code, wire status and the identifying details
    rejected = body["results"][1]
    assert rejected["taskId"] == "task-4"
    assert rejected["error"]["code"] == "INVALID_STATUS_TRANSITION"
    assert rejected["error"]["statusCode"] == 409
    assert rejected["error"]["details"]["currentStatus"] == "DONE"

    # 1. task-1 moved; task-4 is untouched, including its updated_at
    assert _status_of(client, "task-1") == "DONE"
    assert _status_of(client, "task-4") == "DONE"
    assert client.get("/api/tasks/task-4").json()["updated_at"] == before

    # 3 + 4. exactly one event and one audit entry -- the rejected item produced neither
    events = event_bus.published_of(STATUS_CHANGED)
    assert len(events) == 1
    assert events[0].payload["taskId"] == "task-1"
    assert audit_sink.count_for(STATUS_CHANGED) == 1


# -- AC-4 -----------------------------------------------------------------------------------
def test_target_status_outside_done_or_blocked_is_rejected_before_any_write(
    client: TestClient,
) -> None:
    """AC-4: IN_PROGRESS is a valid TaskStatus but not a handover target -> 422, nothing runs."""
    response = client.patch(
        BULK_STATUS_PATH, json={"task_ids": ["task-1", "task-2"], "status": "IN_PROGRESS"}
    )

    assert response.status_code == 422
    body = response.json()
    error = body["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["statusCode"] == 422
    assert error["details"]["requestedStatus"] == "IN_PROGRESS"
    assert error["details"]["permittedStatuses"] == ["BLOCKED", "DONE"]
    assert "results" not in body

    # 1. no task moved -- the rejection precedes every repository write
    assert _status_of(client, "task-1") == "TODO"
    assert _status_of(client, "task-2") == "IN_PROGRESS"

    # 3 + 4. zero events, zero audit entries
    assert len(event_bus.published_of(STATUS_CHANGED)) == 0
    assert audit_sink.count_for(STATUS_CHANGED) == 0


@pytest.mark.parametrize("requested", [TaskStatus.TODO, TaskStatus.IN_PROGRESS])
def test_non_handover_target_raises_validation_error_below_http(
    activities: ActivitiesHarness, requested: TaskStatus
) -> None:
    """AC-4, below HTTP: the allow-list is a service rule, so it holds without a request.

    Asserted against an isolated bus, where "zero events" is a real guarantee rather than a
    consequence of the reset fixture having cleared a shared log.
    """
    with pytest.raises(ValidationError) as caught:
        activities.service.bulk_update_status(["task-1"], requested)

    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.status_code == 422
    assert activities.service.get_task("task-1").status is TaskStatus.TODO
    assert len(activities.bus.published) == 0
    assert len(activities.audit.entries) == 0


# -- AC-5 -----------------------------------------------------------------------------------
def test_all_items_failing_publishes_no_event_and_writes_no_audit_entry(
    client: TestClient,
) -> None:
    """AC-5: the counting invariant in isolation -- a failed item produces neither side effect."""
    before = client.get("/api/tasks/task-4").json()["updated_at"]

    response = client.patch(
        BULK_STATUS_PATH, json={"task_ids": ["task-4", "task-999"], "status": "BLOCKED"}
    )

    # A well-formed request whose items all failed is 207, not 422 (A-2)
    assert response.status_code == 207
    body = response.json()
    assert body["updated"] == 0
    assert body["failed"] == 2
    assert [item["outcome"] for item in body["results"]] == ["FAILED", "FAILED"]

    # 2. each item keeps its own specific code
    assert [item["error"]["code"] for item in body["results"]] == [
        "INVALID_STATUS_TRANSITION",
        "TASK_NOT_FOUND",
    ]

    # 1. nothing changed
    assert _status_of(client, "task-4") == "DONE"
    assert client.get("/api/tasks/task-4").json()["updated_at"] == before

    # 3 + 4. the assertion the whole sprint turns on: zero, not "at least one"
    assert len(event_bus.published_of(STATUS_CHANGED)) == 0
    assert audit_sink.count_for(STATUS_CHANGED) == 0


# -- AC-6 -----------------------------------------------------------------------------------
def test_empty_task_id_list_is_rejected_with_422_and_no_events(client: TestClient) -> None:
    """AC-6: an empty batch is a client error, not a successful no-op returning 200."""
    response = client.patch(BULK_STATUS_PATH, json={"task_ids": [], "status": "DONE"})

    assert response.status_code == 422
    body = response.json()
    error = body["error"]
    assert error["code"] == "VALIDATION_ERROR"
    assert error["statusCode"] == 422

    # A naive loop would return 200 with updated == 0 and satisfy every other criterion
    assert "updated" not in body
    assert "failed" not in body
    assert "results" not in body

    # 3 + 4. zero events, zero audit entries
    assert len(event_bus.published_of(STATUS_CHANGED)) == 0
    assert audit_sink.count_for(STATUS_CHANGED) == 0
