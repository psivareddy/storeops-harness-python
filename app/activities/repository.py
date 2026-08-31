"""activities data access. In-memory; no business rules, no external calls.

A repository never raises a domain error for a missing row -- it returns ``None`` and lets the
service decide that absence means :class:`~app.shared.errors.TaskNotFoundError`. Keeping that
decision in the service is what allows the bulk-status endpoint to treat one missing task as a
partial failure rather than a whole-request failure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.activities.models import Task, TaskCategory, TaskPriority, TaskStatus

_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _seed_tasks() -> list[Task]:
    return [
        Task(
            id="task-1",
            title="Restock beverage aisle end cap",
            store_id="store-101",
            description="Refill end cap after weekend promotion",
            status=TaskStatus.TODO,
            priority=TaskPriority.HIGH,
            category=TaskCategory.RESTOCKING,
            assignee_id="user-3",
            due_at=_NOW + timedelta(hours=6),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        Task(
            id="task-2",
            title="Reset seasonal planogram bay 12",
            store_id="store-101",
            description="Apply autumn planogram to bay 12",
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.PLANOGRAM,
            assignee_id="user-3",
            due_at=_NOW + timedelta(days=1),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        Task(
            id="task-3",
            title="Chilled cabinet temperature audit",
            store_id="store-101",
            description="Record temperatures for all chilled units",
            status=TaskStatus.BLOCKED,
            priority=TaskPriority.CRITICAL,
            category=TaskCategory.COMPLIANCE,
            assignee_id="user-2",
            due_at=_NOW - timedelta(hours=2),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        Task(
            id="task-4",
            title="Weekly shrinkage count",
            store_id="store-102",
            description="Count high-value lines",
            status=TaskStatus.DONE,
            priority=TaskPriority.MEDIUM,
            category=TaskCategory.AUDIT,
            assignee_id="user-4",
            due_at=_NOW - timedelta(days=1),
            created_at=_NOW,
            updated_at=_NOW,
        ),
        Task(
            id="task-5",
            title="Check fire exit signage",
            store_id="store-102",
            description="Verify signage is lit and unobstructed",
            status=TaskStatus.TODO,
            priority=TaskPriority.LOW,
            category=TaskCategory.GENERAL,
            assignee_id=None,
            due_at=None,
            created_at=_NOW,
            updated_at=_NOW,
        ),
    ]


class TaskRepository:
    """In-memory task store keyed by task id."""

    def __init__(self) -> None:
        self._tasks: dict[str, Task] = {}
        self.reset()

    def reset(self) -> None:
        """Restore seed data. Test helper; also used to give each app a clean store."""
        self._tasks = {task.id: task for task in _seed_tasks()}

    def list_all(
        self, *, store_id: str | None = None, status: TaskStatus | None = None
    ) -> list[Task]:
        tasks = list(self._tasks.values())
        if store_id is not None:
            tasks = [task for task in tasks if task.store_id == store_id]
        if status is not None:
            tasks = [task for task in tasks if task.status is status]
        return sorted(tasks, key=lambda task: task.id)

    def get(self, task_id: str) -> Task | None:
        """Return the task, or ``None`` when it does not exist."""
        return self._tasks.get(task_id)

    def add(self, task: Task) -> Task:
        self._tasks[task.id] = task
        return task

    def replace(self, task: Task) -> Task:
        """Overwrite an existing task. Caller has already confirmed it exists."""
        self._tasks[task.id] = task
        return task

    def next_id(self) -> str:
        return f"task-{len(self._tasks) + 1}"

    def count(self) -> int:
        return len(self._tasks)

    def known_store_ids(self) -> frozenset[str]:
        return frozenset(task.store_id for task in self._tasks.values())


task_repository = TaskRepository()
