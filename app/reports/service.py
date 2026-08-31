"""reports business logic — aggregation only.

Every cross-module read goes through a sibling **service**: ``ActivitiesService``,
``ProgrammesService``, ``StaffService``. None of their repositories is imported, which is the
module boundary rule (**Failure Mode 1**) in its intended form.

Nothing here writes: no sibling mutation, no event publication, no report row created. A store
summary is computed and returned, so the read-only guarantee holds at runtime.
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime

from app.activities.models import TaskStatus
from app.activities.service import ActivitiesService, activities_service
from app.programmes.models import ProjectStatus
from app.programmes.service import ProgrammesService, programmes_service
from app.reports.models import Report, ReportType, StoreSummary
from app.reports.repository import ReportRepository, report_repository
from app.shared.errors import StoreNotFoundError
from app.shared.logging import get_logger
from app.staff.service import StaffService, staff_service

logger = get_logger(__name__)


class ReportsService:
    """Read-only aggregation across activities, programmes and staff."""

    def __init__(
        self,
        repository: ReportRepository | None = None,
        activities: ActivitiesService | None = None,
        programmes: ProgrammesService | None = None,
        staff: StaffService | None = None,
    ) -> None:
        self._repository = repository if repository is not None else report_repository
        self._activities = activities if activities is not None else activities_service
        self._programmes = programmes if programmes is not None else programmes_service
        self._staff = staff if staff is not None else staff_service

    def list_reports(self, *, report_type: ReportType | None = None) -> list[Report]:
        return self._repository.list_all(report_type=report_type)

    def get_store_summary(self, store_id: str, *, now: datetime | None = None) -> StoreSummary:
        """Compute a store performance summary.

        Raises :class:`StoreNotFoundError` when no activity references ``store_id`` -- reporting
        on an unknown store would silently return a zeroed summary that reads like a healthy
        store with no work outstanding.
        """
        if store_id not in self._activities.known_store_ids():
            raise StoreNotFoundError(store_id)

        moment = now if now is not None else datetime.now(UTC)
        tasks = self._activities.tasks_for_store(store_id)

        completed = [task for task in tasks if task.status is TaskStatus.DONE]
        blocked = [task for task in tasks if task.status is TaskStatus.BLOCKED]
        overdue = [
            task
            for task in tasks
            if task.due_at is not None
            and task.due_at < moment
            and task.status is not TaskStatus.DONE
        ]
        overdue_by_category = Counter(task.category.value for task in overdue)

        programmes = self._programmes.projects_for_store(store_id)
        active_programmes = [
            project for project in programmes if project.status is ProjectStatus.ACTIVE
        ]
        staff = self._staff.users_for_store(store_id)

        summary = StoreSummary(
            store_id=store_id,
            total_tasks=len(tasks),
            completed_tasks=len(completed),
            completion_rate=(len(completed) / len(tasks)) if tasks else 0.0,
            overdue_count=len(overdue),
            overdue_by_category=dict(sorted(overdue_by_category.items())),
            blocked_task_ids=[task.id for task in blocked],
            active_programmes=len(active_programmes),
            staff_count=len(staff),
            generated_at=moment,
        )
        logger.info(
            "Store summary computed for %s: %d tasks, %d overdue",
            store_id,
            summary.total_tasks,
            summary.overdue_count,
        )
        return summary


reports_service = ReportsService()
