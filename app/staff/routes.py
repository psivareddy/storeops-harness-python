"""staff HTTP layer: validation and delegation only.

Exposes reads only. Staff records are not writable over the API in the baseline, which mirrors
the module's read-only-to-siblings contract.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.staff.models import StaffRole, User
from app.staff.service import staff_service

router = APIRouter(prefix="/api/users", tags=["staff"])


@router.get("", response_model=list[User])
def list_users(
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
    role: Annotated[StaffRole | None, Query(description="Filter by staff role")] = None,
) -> list[User]:
    """List store staff, optionally filtered by store and role."""
    return staff_service.list_users(store_id=store_id, role=role)
