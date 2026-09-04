"""activities business logic.

All task business rules live here -- never in ``routes.py`` (which validates and delegates) and
never in ``repository.py`` (which persists). Cross-module side effects are published to the
event bus; this module imports no sibling module's repository.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.activities.models import (
    HANDOVER_TARGET_STATUSES,
    BulkItemOutcome,
    BulkStatusItemResult,
    BulkStatusResult,
    Task,
    TaskCreate,
    TaskStatus,
    can_transition,
    is_handover_target,
)
from app.activities.repository import TaskRepository, task_repository
from app.shared.errors import (
    AppError,
    InvalidStatusTransitionError,
    TaskNotFoundError,
    ValidationError,
)
from app.shared.events import EventBus, EventName, event_bus
from app.shared.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from collections.abc import Sequence

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


    def bulk_update_status(
        self, task_ids: Sequence[str], requested: TaskStatus
    ) -> BulkStatusResult:
        """Move many activities to ``requested``, isolating each item's failure.

        Request-level rejections (an empty batch, a target outside
        :data:`~app.activities.models.HANDOVER_TARGET_STATUSES`) raise before any write, so
        nothing is persisted and no event is published.

        Per item this delegates to :meth:`update_status`, which means each *successful* update
        publishes exactly one ``ACTIVITY_STATUS_CHANGED`` event -- and therefore produces
        exactly one audit entry, since ``AuditSink`` is subscribed to the bus. A failed item
        never reaches the publish, so it produces neither. That counting invariant falls out of
        reuse rather than being re-established here, where it could be re-broken.
        """
        if not task_ids:
            raise ValidationError(
                "A bulk status update requires at least one task id",
                details={"taskIdCount": 0},
            )
        if not is_handover_target(requested):
            permitted = sorted(status.value for status in HANDOVER_TARGET_STATUSES)
            raise ValidationError(
                f"Bulk status updates may only target {' or '.join(permitted)}; "
                f"got {requested.value}",
                details={"requestedStatus": requested.value, "permittedStatuses": permitted},
            )

        results: list[BulkStatusItemResult] = []
        updated = 0
        for task_id in task_ids:
            try:
                task = self.update_status(task_id, requested)
            except AppError as exc:
                # Permitted here only: a bulk aggregator in the service layer converting a
                # per-item failure into a per-item result. Never in a route, and never wider
                # than AppError -- a broad catch would swallow the defects the gate exists to
                # find. exc.code is re-surfaced so the item keeps its specific code.
                results.append(
                    BulkStatusItemResult(
                        task_id=task_id,
                        outcome=BulkItemOutcome.FAILED,
                        status=self._current_status(task_id),
                        error=exc.to_payload(),
                    )
                )
            else:
                updated += 1
                results.append(
                    BulkStatusItemResult(
                        task_id=task_id,
                        outcome=BulkItemOutcome.UPDATED,
                        status=task.status,
                    )
                )

        failed = len(results) - updated
        logger.info(
            "Bulk handover to %s: %d updated, %d failed", requested.value, updated, failed
        )
        return BulkStatusResult(updated=updated, failed=failed, results=results)

    def _current_status(self, task_id: str) -> TaskStatus | None:
        """The task's status now, or ``None`` if it does not exist.

        Used to report a failed item's unchanged state without raising a second time.
        """
        task = self._repository.get(task_id)
        return task.status if task is not None else None


activities_service = ActivitiesService()
