"""activities HTTP layer: validation and delegation only.

This module imports ``service`` and never ``repository``. Business rules -- including which
status transitions are legal -- live in the service, so the same rule applies whether a change
arrives over HTTP or from an event handler.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.activities.models import (
    BulkStatusResult,
    BulkStatusUpdate,
    Task,
    TaskCreate,
    TaskStatus,
    TaskStatusUpdate,
)
from app.activities.service import activities_service

tasks_router = APIRouter(prefix="/api/tasks", tags=["activities"])
bulk_router = APIRouter(prefix="/api/activities", tags=["activities"])


@tasks_router.get("", response_model=list[Task])
def list_tasks(
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> list[Task]:
    """List operational activities, optionally filtered by store and status."""
    return activities_service.list_tasks(store_id=store_id, status=task_status)


@tasks_router.get("/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    """Fetch a single activity. Raises ``TASK_NOT_FOUND`` when absent."""
    return activities_service.get_task(task_id)


@tasks_router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> Task:
    """Create an operational activity."""
    return activities_service.create_task(payload)


@tasks_router.patch("/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    """Change an activity's status, publishing one ``ACTIVITY_STATUS_CHANGED`` event."""
    return activities_service.update_status(task_id, payload.status)


@bulk_router.patch("/bulk-status", response_model=BulkStatusResult)
def bulk_update_task_status(payload: BulkStatusUpdate, response: Response) -> BulkStatusResult:
    """Shift handover: move many activities to DONE or BLOCKED in one request.

    Returns 200 when every item transitioned and 207 when any did not. Selecting the status
    from the result shape is presentation, not a business rule -- which item failed and why is
    decided entirely in the service.
    """
    result = activities_service.bulk_update_status(payload.task_ids, payload.status)
    response.status_code = (
        status.HTTP_207_MULTI_STATUS if result.failed else status.HTTP_200_OK
    )
    return result


#: The module's public routing surface. ``app/main.py`` includes this single object, so the
#: second prefix needed by ``PATCH /api/activities/bulk-status`` -- which cannot live under
#: ``/api/tasks`` -- is registered without changing the composition root.
router = APIRouter()
router.include_router(tasks_router)
router.include_router(bulk_router)
