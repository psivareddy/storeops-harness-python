"""reports aggregation — cross-module reads through sibling service layers only."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.reports.models import ReportType
from app.reports.service import ReportsService
from app.shared.errors import StoreNotFoundError

#: Fixed clock. task-3 (due -2h) is overdue at this moment; task-1 (due +6h) is not.
NOW = datetime(2026, 8, 31, 12, 0, tzinfo=UTC)


@pytest.fixture
def service() -> ReportsService:
    return ReportsService()


def test_store_summary_aggregates_tasks_programmes_and_staff(service: ReportsService) -> None:
    summary = service.get_store_summary("store-101", now=NOW)

    # activities: task-1 TODO, task-2 IN_PROGRESS, task-3 BLOCKED
    assert summary.total_tasks == 3
    assert summary.completed_tasks == 0
    assert summary.completion_rate == 0.0
    assert summary.blocked_task_ids == ["task-3"]

    # programmes: project-1 ACTIVE, project-2 PLANNED
    assert summary.active_programmes == 1

    # staff: user-1, user-2, user-3
    assert summary.staff_count == 3


def test_completion_rate_reflects_completed_work(service: ReportsService) -> None:
    summary = service.get_store_summary("store-102", now=NOW)

    # store-102 has task-4 DONE and task-5 TODO
    assert summary.total_tasks == 2
    assert summary.completed_tasks == 1
    assert summary.completion_rate == pytest.approx(0.5)


def test_overdue_counts_are_grouped_by_category_and_exclude_completed_work(
    service: ReportsService,
) -> None:
    """task-3 is COMPLIANCE and past due. task-4 is also past due but DONE, so it must not be
    counted -- completed late work is not outstanding work."""
    store_101 = service.get_store_summary("store-101", now=NOW)
    assert store_101.overdue_count == 1
    assert store_101.overdue_by_category == {"COMPLIANCE": 1}

    store_102 = service.get_store_summary("store-102", now=NOW)
    assert store_102.overdue_count == 0
    assert store_102.overdue_by_category == {}


def test_summary_reflects_a_task_completed_through_the_activities_service(
    service: ReportsService,
) -> None:
    """Proves the aggregation reads live state through the sibling service rather than a cached
    or duplicated copy."""
    from app.activities.models import TaskStatus
    from app.activities.service import ActivitiesService

    ActivitiesService().update_status("task-1", TaskStatus.DONE)

    summary = service.get_store_summary("store-101", now=NOW)
    assert summary.completed_tasks == 1
    assert summary.completion_rate == pytest.approx(1 / 3)


def test_unknown_store_raises_rather_than_returning_a_zeroed_summary(
    service: ReportsService,
) -> None:
    """A zeroed summary would read like a healthy store with no outstanding work."""
    with pytest.raises(StoreNotFoundError) as caught:
        service.get_store_summary("store-999", now=NOW)

    assert caught.value.code == "STORE_NOT_FOUND"
    assert caught.value.status_code == 404
    assert caught.value.details == {"storeId": "store-999"}


def test_list_reports_filters_by_type(service: ReportsService) -> None:
    assert len(service.list_reports()) == 2
    rollups = service.list_reports(report_type=ReportType.REGIONAL_ROLLUP)
    assert [report.id for report in rollups] == ["report-2"]


def test_generated_at_uses_the_supplied_clock(service: ReportsService) -> None:
    assert service.get_store_summary("store-101", now=NOW).generated_at == NOW


def test_default_clock_is_used_when_none_supplied(service: ReportsService) -> None:
    summary = service.get_store_summary("store-101")

    assert summary.generated_at.tzinfo is not None


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def test_store_summary_endpoint_returns_the_aggregation(client: TestClient) -> None:
    response = client.get("/api/reports/store/store-101")

    assert response.status_code == 200
    body = response.json()
    assert body["store_id"] == "store-101"
    assert body["total_tasks"] == 3
    assert body["blocked_task_ids"] == ["task-3"]
    assert body["active_programmes"] == 1
    assert body["staff_count"] == 3


def test_store_summary_endpoint_returns_the_typed_envelope_for_unknown_store(
    client: TestClient,
) -> None:
    response = client.get("/api/reports/store/store-999")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "STORE_NOT_FOUND"
