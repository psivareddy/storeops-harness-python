"""reports domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ReportType(StrEnum):
    STORE_SUMMARY = "STORE_SUMMARY"
    REGIONAL_ROLLUP = "REGIONAL_ROLLUP"
    DEPARTMENT_PERFORMANCE = "DEPARTMENT_PERFORMANCE"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


class Report(BaseModel):
    """A persisted report record.

    Records are seeded, never created by this module -- reports is read-only.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    report_type: ReportType
    status: ReportStatus
    scope_id: str
    requested_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StoreSummary(BaseModel):
    """A store performance summary, computed on demand and never persisted.

    Returning a computed value rather than writing a ``Report`` row is what keeps the read-only
    guarantee true at runtime rather than only by convention.
    """

    model_config = ConfigDict(frozen=True)

    store_id: str
    total_tasks: int
    completed_tasks: int
    completion_rate: float = Field(ge=0.0, le=1.0)
    overdue_count: int
    overdue_by_category: dict[str, int]
    blocked_task_ids: list[str]
    active_programmes: int
    staff_count: int
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
