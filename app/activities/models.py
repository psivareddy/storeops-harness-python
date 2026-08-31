"""activities domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

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
