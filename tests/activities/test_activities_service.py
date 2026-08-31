"""activities business rules.

Every test asserts the four things the harness requires: resulting state, error code, published
events, and audit entry count. A test that only asserted "it did not raise" would be the unit
equivalent of Failure Mode 3.
"""

from __future__ import annotations

import pytest

from app.activities.models import (
    ALLOWED_TRANSITIONS,
    Task,
    TaskCategory,
    TaskCreate,
    TaskPriority,
    TaskStatus,
    can_transition,
)
from app.shared.errors import InvalidStatusTransitionError, TaskNotFoundError
from app.shared.events import EventName
from tests.conftest import ActivitiesHarness


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------
def test_done_is_terminal() -> None:
    """A completed activity is an audit record; reopening it would rewrite history."""
    assert ALLOWED_TRANSITIONS[TaskStatus.DONE] == frozenset()
    for target in TaskStatus:
        assert can_transition(TaskStatus.DONE, target) is False


@pytest.mark.parametrize("current", [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED])
def test_same_status_is_never_a_valid_transition(current: TaskStatus) -> None:
    """A no-op update would publish an ACTIVITY_STATUS_CHANGED event describing no change."""
    assert can_transition(current, current) is False


@pytest.mark.parametrize("current", [TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED])
def test_every_open_status_can_reach_done(current: TaskStatus) -> None:
    assert can_transition(current, TaskStatus.DONE) is True


# ---------------------------------------------------------------------------
# update_status — the happy path
# ---------------------------------------------------------------------------
def test_update_status_changes_state_publishes_one_event_and_writes_one_audit_entry(
    activities: ActivitiesHarness,
) -> None:
    before = activities.service.get_task("task-1")
    assert before.status is TaskStatus.TODO

    updated = activities.service.update_status("task-1", TaskStatus.DONE)

    # resulting state
    assert updated.status is TaskStatus.DONE
    assert activities.service.get_task("task-1").status is TaskStatus.DONE
    assert updated.updated_at > before.updated_at

    # exactly one event, carrying both statuses
    events = activities.bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)
    assert len(events) == 1
    assert events[0].payload["taskId"] == "task-1"
    assert events[0].payload["previousStatus"] == "TODO"
    assert events[0].payload["newStatus"] == "DONE"

    # exactly one audit entry
    assert activities.audit.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 1


def test_each_update_publishes_exactly_one_event_so_counts_track_updates(
    activities: ActivitiesHarness,
) -> None:
    """The invariant the bulk-status endpoint will rely on: N successful updates produce N
    events and N audit entries, never N+1."""
    activities.service.update_status("task-1", TaskStatus.DONE)
    activities.service.update_status("task-2", TaskStatus.BLOCKED)
    activities.service.update_status("task-3", TaskStatus.DONE)

    assert len(activities.bus.published_of(EventName.ACTIVITY_STATUS_CHANGED)) == 3
    assert activities.audit.count_for(EventName.ACTIVITY_STATUS_CHANGED) == 3


# ---------------------------------------------------------------------------
# update_status — failure paths publish nothing
# ---------------------------------------------------------------------------
def test_unknown_task_raises_task_not_found_and_publishes_no_event(
    activities: ActivitiesHarness,
) -> None:
    with pytest.raises(TaskNotFoundError) as caught:
        activities.service.update_status("task-does-not-exist", TaskStatus.DONE)

    assert caught.value.code == "TASK_NOT_FOUND"
    assert caught.value.status_code == 404
    assert caught.value.details == {"taskId": "task-does-not-exist"}
    assert len(activities.bus.published) == 0
    assert len(activities.audit.entries) == 0


def test_transition_from_done_raises_conflict_and_leaves_state_and_logs_untouched(
    activities: ActivitiesHarness,
) -> None:
    with pytest.raises(InvalidStatusTransitionError) as caught:
        activities.service.update_status("task-4", TaskStatus.TODO)

    assert caught.value.code == "INVALID_STATUS_TRANSITION"
    assert caught.value.status_code == 409
    assert caught.value.details["currentStatus"] == "DONE"
    assert caught.value.details["requestedStatus"] == "TODO"

    # state unchanged, and no event or audit entry for a rejected change
    assert activities.service.get_task("task-4").status is TaskStatus.DONE
    assert len(activities.bus.published) == 0
    assert len(activities.audit.entries) == 0


def test_no_op_update_is_rejected_and_publishes_nothing(
    activities: ActivitiesHarness,
) -> None:
    with pytest.raises(InvalidStatusTransitionError):
        activities.service.update_status("task-1", TaskStatus.TODO)

    assert len(activities.bus.published) == 0


# ---------------------------------------------------------------------------
# create_task
# ---------------------------------------------------------------------------
def test_create_task_persists_defaults_and_publishes_activity_created(
    activities: ActivitiesHarness,
) -> None:
    before = activities.repository.count()

    created = activities.service.create_task(
        TaskCreate(
            title="Check chilled aisle temperatures",
            store_id="store-101",
            priority=TaskPriority.CRITICAL,
            category=TaskCategory.COMPLIANCE,
            assignee_id="user-3",
        )
    )

    assert created.status is TaskStatus.TODO  # new work always starts as TODO
    assert created.priority is TaskPriority.CRITICAL
    assert activities.repository.count() == before + 1
    assert activities.service.get_task(created.id).title == "Check chilled aisle temperatures"

    events = activities.bus.published_of(EventName.ACTIVITY_CREATED)
    assert len(events) == 1
    assert events[0].payload["taskId"] == created.id
    assert events[0].payload["category"] == "COMPLIANCE"
    assert activities.audit.count_for(EventName.ACTIVITY_CREATED) == 1


# ---------------------------------------------------------------------------
# reads
# ---------------------------------------------------------------------------
def test_get_task_raises_typed_error_rather_than_returning_none(
    activities: ActivitiesHarness,
) -> None:
    with pytest.raises(TaskNotFoundError):
        activities.service.get_task("nope")


def test_list_tasks_filters_by_store_and_status(activities: ActivitiesHarness) -> None:
    store_101 = activities.service.list_tasks(store_id="store-101")
    assert {task.store_id for task in store_101} == {"store-101"}
    assert len(store_101) == 3

    todo_only = activities.service.list_tasks(status=TaskStatus.TODO)
    assert {task.status for task in todo_only} == {TaskStatus.TODO}

    combined = activities.service.list_tasks(store_id="store-102", status=TaskStatus.TODO)
    assert [task.id for task in combined] == ["task-5"]


def test_tasks_for_store_and_known_store_ids_back_the_reports_aggregation(
    activities: ActivitiesHarness,
) -> None:
    assert activities.service.known_store_ids() == frozenset({"store-101", "store-102"})
    assert len(activities.service.tasks_for_store("store-102")) == 2


def test_is_open_reflects_completion() -> None:
    open_task = Task(id="t", title="t", store_id="s", status=TaskStatus.BLOCKED)
    done_task = Task(id="t", title="t", store_id="s", status=TaskStatus.DONE)

    assert open_task.is_open is True
    assert done_task.is_open is False
