"""programmes HTTP layer: validation and delegation only."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.programmes.models import Project, ProjectMemberCreate
from app.programmes.service import programmes_service

router = APIRouter(prefix="/api/projects", tags=["programmes"])


@router.get("", response_model=list[Project])
def list_projects(
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
) -> list[Project]:
    """List store programmes, optionally filtered by store."""
    return programmes_service.list_projects(store_id=store_id)


@router.post(
    "/{project_id}/members", response_model=Project, status_code=status.HTTP_201_CREATED
)
def add_project_member(project_id: str, payload: ProjectMemberCreate) -> Project:
    """Enrol a staff member on a programme, publishing ``PROGRAMME_MEMBER_ADDED``."""
    return programmes_service.add_member(project_id, payload)
