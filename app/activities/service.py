"""activities business logic.

All task business rules live here -- never in ``routes.py`` (which validates and delegates) and
never in ``repository.py`` (which persists). Cross-module side effects are published to the
event bus; this module imports no sibling module's repository.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.activities.models import Task, TaskCreate, TaskStatus, can_transition
from app.activities.repository import TaskRepository, task_repository
from app.shared.errors import InvalidStatusTransitionError, TaskNotFoundError
from app.shared.events import EventBus, EventName, event_bus
from app.shared.logging import get_logger

logger = get_logger(__name__)


class ActivitiesService:
    """Read and write operations for operational activities."""

    def __init__(
        self, repository: TaskRepository | None = None, bus: EventBus | None = None
    ) -> None:
        self._repository = repository if repository is not None else task_repository
        self._bus = bus if bus is not None else event_bus

    # -- reads ------------------------------------------------------------------
    def list_tasks(
        self, *, store_id: str | None = None, status: TaskStatus | None = None
    ) -> list[Task]:
        return self._repository.list_all(store_id=store_id, status=status)

    def get_task(self, task_id: str) -> Task:
        """Return a task or raise :class:`TaskNotFoundError`.

        This is the read entry point sibling modules use. ``reports`` calls it rather than
        importing ``TaskRepository``, which is the module boundary rule in practice.
        """
        task = self._repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)
        return task

    def tasks_for_store(self, store_id: str) -> list[Task]:
        return self._repository.list_all(store_id=store_id)

    def known_store_ids(self) -> frozenset[str]:
        return self._repository.known_store_ids()

    # -- writes -----------------------------------------------------------------
    def create_task(self, payload: TaskCreate) -> Task:
        """Create a task and publish ``ACTIVITY_CREATED``."""
        now = datetime.now(UTC)
        task = Task(
            id=self._repository.next_id(),
            title=payload.title,
            store_id=payload.store_id,
            description=payload.description,
            status=TaskStatus.TODO,
            priority=payload.priority,
            category=payload.category,
            assignee_id=payload.assignee_id,
            due_at=payload.due_at,
            created_at=now,
            updated_at=now,
        )
        self._repository.add(task)
        self._bus.publish(
            EventName.ACTIVITY_CREATED,
            {
                "taskId": task.id,
                "storeId": task.store_id,
                "priority": task.priority.value,
                "category": task.category.value,
                "assigneeId": task.assignee_id,
            },
        )
        logger.info("Task %s created for store %s", task.id, task.store_id)
        return task

    def update_status(self, task_id: str, requested: TaskStatus) -> Task:
        """Move a task to ``requested``, publishing exactly one event on success.

        Raises :class:`TaskNotFoundError` when the task does not exist and
        :class:`InvalidStatusTransitionError` when the transition is not permitted. In both
        cases **no event is published and no audit entry is written** -- the guarantee the
        bulk-status endpoint depends on for its per-item partial-failure semantics.
        """
        task = self.get_task(task_id)
        if not can_transition(task.status, requested):
            raise InvalidStatusTransitionError(task_id, task.status.value, requested.value)

        previous = task.status
        updated = task.model_copy(update={"status": requested, "updated_at": datetime.now(UTC)})
        self._repository.replace(updated)
        self._bus.publish(
            EventName.ACTIVITY_STATUS_CHANGED,
            {
                "taskId": updated.id,
                "storeId": updated.store_id,
                "previousStatus": previous.value,
                "newStatus": requested.value,
                "priority": updated.priority.value,
                "assigneeId": updated.assignee_id,
            },
        )
        logger.info("Task %s moved %s -> %s", task_id, previous.value, requested.value)
        return updated


activities_service = ActivitiesService()
