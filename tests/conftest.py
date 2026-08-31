"""Shared test fixtures.

The state-reset fixture lives here rather than in ``app/`` deliberately: a reset registry that
imported every business module would have to live in ``app/shared/``, which is forbidden from
importing business modules. Keeping it in the test tree preserves that boundary.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from app.activities.repository import TaskRepository, task_repository
from app.activities.service import ActivitiesService
from app.alerts.repository import NotificationRepository, notification_repository
from app.alerts.service import AlertsService
from app.main import create_app
from app.programmes.repository import project_repository
from app.reports.repository import report_repository
from app.shared.audit import AuditSink, audit_sink
from app.shared.events import EventBus, event_bus
from app.staff.repository import user_repository


@pytest.fixture(autouse=True)
def reset_state() -> Iterator[None]:
    """Restore seed data and clear observability logs around every test.

    Subscriptions are intentionally *not* reset: they are wired once by the application factory,
    and dropping them would make the event-driven alert tests pass for the wrong reason.
    """
    task_repository.reset()
    project_repository.reset()
    user_repository.reset()
    notification_repository.reset()
    report_repository.reset()
    event_bus.clear_log()
    audit_sink.clear()
    yield
    event_bus.clear_log()
    audit_sink.clear()


@pytest.fixture
def client() -> Iterator[TestClient]:
    """An HTTP client over a freshly built application."""
    with TestClient(create_app()) as test_client:
        yield test_client


def api_endpoints(client: TestClient, prefix: str = "/api/") -> set[tuple[str, str]]:
    """Every published REST endpoint as ``(METHOD, path)``, read from the OpenAPI schema.

    Deliberately not derived from ``app.routes``: Starlette 1.6 wraps included routers in an
    internal optimisation object with no ``.path``, so walking the route table is version
    -fragile. The OpenAPI document is the published contract and is the thing worth asserting.
    """
    schema = client.get("/openapi.json").json()
    return {
        (method.upper(), path)
        for path, operations in schema["paths"].items()
        if path.startswith(prefix)
        for method in operations
        if method.upper() not in {"HEAD", "OPTIONS"}
    }


def endpoint_tags(client: TestClient) -> set[str]:
    """Every tag attached to a published operation."""
    schema = client.get("/openapi.json").json()
    return {
        tag
        for operations in schema["paths"].values()
        for operation in operations.values()
        for tag in operation.get("tags", [])
    }


@dataclass(frozen=True, slots=True)
class ActivitiesHarness:
    """An isolated activities service with its own bus, repository and audit sink.

    Used by unit tests that need to assert "no event was published" without interference from
    the process-wide bus.
    """

    service: ActivitiesService
    repository: TaskRepository
    bus: EventBus
    audit: AuditSink


@pytest.fixture
def activities() -> ActivitiesHarness:
    bus = EventBus()
    repository = TaskRepository()
    audit = AuditSink()
    audit.attach(bus)
    return ActivitiesHarness(
        service=ActivitiesService(repository=repository, bus=bus),
        repository=repository,
        bus=bus,
        audit=audit,
    )


@dataclass(frozen=True, slots=True)
class AlertsHarness:
    """An isolated alerts service subscribed to its own bus."""

    service: AlertsService
    repository: NotificationRepository
    bus: EventBus


@pytest.fixture
def alerts() -> AlertsHarness:
    bus = EventBus()
    repository = NotificationRepository()
    service = AlertsService(repository=repository, bus=bus)
    service.register_event_handlers(bus)
    return AlertsHarness(service=service, repository=repository, bus=bus)
