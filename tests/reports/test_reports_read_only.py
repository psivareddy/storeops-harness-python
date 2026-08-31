"""The read-only-reports guarantee (HG-6), asserted three independent ways.

``lint-imports`` proves reports never *imports* a sibling repository. These tests prove the
stronger property the rule actually cares about: no write can *originate* in reports.
"""

from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from app.activities.repository import task_repository
from app.alerts.repository import notification_repository
from app.programmes.repository import project_repository
from app.reports.repository import FORBIDDEN_WRITE_METHODS, ReportRepository
from app.reports.service import ReportsService
from app.shared.audit import audit_sink
from app.shared.events import event_bus
from app.staff.repository import user_repository
from tests.conftest import api_endpoints


def test_report_repository_exposes_no_write_method() -> None:
    """Enforced by the shape of the class: a Generator cannot call an API that does not exist."""
    public_methods = {
        name for name, _ in inspect.getmembers(ReportRepository, inspect.isfunction)
        if not name.startswith("_")
    }

    offending = public_methods & FORBIDDEN_WRITE_METHODS
    assert offending == set(), f"reports repository gained write methods: {sorted(offending)}"
    assert public_methods == {"list_all", "get", "count", "reset"}


def test_reports_service_exposes_no_write_method() -> None:
    public_methods = {
        name for name, _ in inspect.getmembers(ReportsService, inspect.isfunction)
        if not name.startswith("_")
    }

    assert public_methods & FORBIDDEN_WRITE_METHODS == set()
    assert public_methods == {"list_reports", "get_store_summary"}


def test_generating_a_summary_mutates_no_sibling_module() -> None:
    """The behavioural assertion: aggregation must leave every sibling repository untouched."""
    before = (
        task_repository.count(),
        project_repository.count(),
        user_repository.count(),
        notification_repository.count(),
    )

    ReportsService().get_store_summary("store-101")

    after = (
        task_repository.count(),
        project_repository.count(),
        user_repository.count(),
        notification_repository.count(),
    )
    assert before == after


def test_generating_a_summary_publishes_no_event_and_writes_no_audit_entry() -> None:
    """reports must raise no mutation events. A read that emits an event would appear in the
    audit trail as a state change that never happened."""
    ReportsService().get_store_summary("store-101")

    assert len(event_bus.published) == 0
    assert len(audit_sink.entries) == 0


def test_generating_a_summary_creates_no_report_row() -> None:
    """A store summary is computed and returned, never persisted."""
    from app.reports.repository import report_repository

    before = report_repository.count()

    ReportsService().get_store_summary("store-101")

    assert report_repository.count() == before


def test_reports_router_exposes_only_read_methods(client: TestClient) -> None:
    endpoints = api_endpoints(client, prefix="/api/reports")

    assert endpoints == {("GET", "/api/reports/store/{store_id}")}
    assert {method for method, _ in endpoints} == {"GET"}


def test_write_verbs_against_the_reports_endpoint_are_not_routed(client: TestClient) -> None:
    for verb in ("post", "put", "patch", "delete"):
        response = getattr(client, verb)("/api/reports/store/store-101")
        assert response.status_code == 405, f"{verb.upper()} unexpectedly routed"
