"""reports HTTP layer: validation and delegation only.

GET only. There is no POST, PATCH, PUT or DELETE on this router, which is the HTTP-level
expression of the read-only-reports rule.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.reports.models import StoreSummary
from app.reports.service import reports_service

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/store/{store_id}", response_model=StoreSummary)
def get_store_summary(store_id: str) -> StoreSummary:
    """Aggregate task completion, overdue counts by category, and blocked activities."""
    return reports_service.get_store_summary(store_id)
