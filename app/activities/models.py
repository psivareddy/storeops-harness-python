"""activities domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    BLOCKED = "BLOCKED"


class TaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class TaskCategory(StrEnum):
    RESTOCKING = "RESTOCKING"
    PLANOGRAM = "PLANOGRAM"
    AUDIT = "AUDIT"
    COMPLIANCE = "COMPLIANCE"
    GENERAL = "GENERAL"


#: Permitted status transitions. ``DONE`` is terminal: a completed activity is an audit record,
#: so reopening it would silently rewrite history. A same-status update is also rejected -- it
#: would publish an ``ACTIVITY_STATUS_CHANGED`` event describing no change.
ALLOWED_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.TODO: frozenset({TaskStatus.IN_PROGRESS, TaskStatus.BLOCKED, TaskStatus.DONE}),
    TaskStatus.IN_PROGRESS: frozenset({TaskStatus.TODO, TaskStatus.BLOCKED, TaskStatus.DONE}),
    TaskStatus.BLOCKED: frozenset({TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE}),
    TaskStatus.DONE: frozenset(),
}


def can_transition(current: TaskStatus, requested: TaskStatus) -> bool:
    """Whether ``current`` may move to ``requested``."""
    return requested in ALLOWED_TRANSITIONS[current]


class Task(BaseModel):
    """An operational activity assigned to store staff."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    store_id: str
    description: str = ""
    status: TaskStatus = TaskStatus.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    category: TaskCategory = TaskCategory.GENERAL
    assignee_id: str | None = None
    due_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_open(self) -> bool:
        return self.status is not TaskStatus.DONE


class TaskCreate(BaseModel):
    """Route-layer input schema for creating a task."""

    title: str = Field(min_length=1, max_length=200)
    store_id: str = Field(min_length=1)
    description: str = ""
    priority: TaskPriority = TaskPriority.MEDIUM
    category: TaskCategory = TaskCategory.GENERAL
    assignee_id: str | None = None
    due_at: datetime | None = None


class TaskStatusUpdate(BaseModel):
    """Route-layer input schema for a single status change."""

    status: TaskStatus


#: Statuses a shift handover may move an activity to. Handover records work as finished or
#: stuck; reopening an activity to ``TODO``/``IN_PROGRESS`` is a different operation with a
#: different authorisation question, so those targets are rejected before any write.
HANDOVER_TARGET_STATUSES: frozenset[TaskStatus] = frozenset(
    {TaskStatus.DONE, TaskStatus.BLOCKED}
)


def is_handover_target(requested: TaskStatus) -> bool:
    """Whether ``requested`` is a status a bulk handover may set.

    Lives beside :func:`can_transition` so both rules are applied by the service and by any
    future event handler, rather than being restated at each call site.
    """
    return requested in HANDOVER_TARGET_STATUSES


class BulkItemOutcome(StrEnum):
    """Per-item outcome within a bulk handover response."""

    UPDATED = "UPDATED"
    FAILED = "FAILED"


class BulkStatusUpdate(BaseModel):
    """Route-layer input schema for a bulk handover status change.

    ``task_ids`` carries no ``min_length``: the empty-batch rejection is a business rule raised
    by the service, so it returns the StoreOps error envelope and stays assertable below HTTP.
    A ``Field`` constraint would have FastAPI reject it first, with a different body shape.
    """

    task_ids: list[str]
    status: TaskStatus


class BulkStatusItemResult(BaseModel):
    """The outcome of one activity within a bulk request."""

    model_config = ConfigDict(frozen=True)

    task_id: str = Field(serialization_alias="taskId")
    outcome: BulkItemOutcome
    status: TaskStatus | None = None
    error: dict[str, Any] | None = None


class BulkStatusResult(BaseModel):
    """Aggregate outcome of a bulk handover request, in request order."""

    model_config = ConfigDict(frozen=True)

    updated: int
    failed: int
    results: list[BulkStatusItemResult]
