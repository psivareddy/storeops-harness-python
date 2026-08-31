"""activities HTTP layer: validation and delegation only.

This module imports ``service`` and never ``repository``. Business rules -- including which
status transitions are legal -- live in the service, so the same rule applies whether a change
arrives over HTTP or from an event handler.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.activities.models import Task, TaskCreate, TaskStatus, TaskStatusUpdate
from app.activities.service import activities_service

router = APIRouter(prefix="/api/tasks", tags=["activities"])


@router.get("", response_model=list[Task])
def list_tasks(
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
    task_status: Annotated[TaskStatus | None, Query(alias="status")] = None,
) -> list[Task]:
    """List operational activities, optionally filtered by store and status."""
    return activities_service.list_tasks(store_id=store_id, status=task_status)


@router.get("/{task_id}", response_model=Task)
def get_task(task_id: str) -> Task:
    """Fetch a single activity. Raises ``TASK_NOT_FOUND`` when absent."""
    return activities_service.get_task(task_id)


@router.post("", response_model=Task, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate) -> Task:
    """Create an operational activity."""
    return activities_service.create_task(payload)


@router.patch("/{task_id}/status", response_model=Task)
def update_task_status(task_id: str, payload: TaskStatusUpdate) -> Task:
    """Change an activity's status, publishing one ``ACTIVITY_STATUS_CHANGED`` event."""
    return activities_service.update_status(task_id, payload.status)
