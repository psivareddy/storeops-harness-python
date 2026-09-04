"""Application wiring: health probe, the endpoint inventory, and event subscription."""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import API_VERSION, create_app, wire_event_handlers
from app.shared.config import Settings
from app.shared.events import EventName, event_bus
from tests.conftest import api_endpoints, endpoint_tags

#: Every published REST endpoint, excluding /health. The 9 required by capstone PDF
#: section 2.3, plus PATCH /api/activities/bulk-status added by sprint-1 (contract D-7).
#: Asserted for exact equality, so adding an endpoint is a deliberate edit here.
EXPECTED_ENDPOINTS = {
    ("GET", "/api/tasks"),
    ("GET", "/api/tasks/{task_id}"),
    ("POST", "/api/tasks"),
    ("PATCH", "/api/tasks/{task_id}/status"),
    ("GET", "/api/projects"),
    ("POST", "/api/projects/{project_id}/members"),
    ("GET", "/api/users"),
    ("GET", "/api/notifications"),
    ("GET", "/api/reports/store/{store_id}"),
    ("PATCH", "/api/activities/bulk-status"),
}


def test_health_endpoint_reports_ready(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["version"] == API_VERSION
    assert body["environment"] == "local"


def test_health_reflects_injected_settings() -> None:
    settings = Settings(app_name="StoreOps Prod", environment="production")

    with TestClient(create_app(settings)) as client:
        body = client.get("/health").json()

    assert body["app"] == "StoreOps Prod"
    assert body["environment"] == "production"


def test_exactly_the_expected_rest_endpoints_are_routed(client: TestClient) -> None:
    """PDF section 2.3 specifies 9 REST endpoints; sprint-1 adds a 10th. /health is excluded."""
    routed = api_endpoints(client)

    assert routed == EXPECTED_ENDPOINTS
    assert len(routed) == 10


def test_the_pdf_verification_endpoint_responds(client: TestClient) -> None:
    """PDF section 2.3 step 4 verifies the baseline with GET /api/tasks -> 200."""
    assert client.get("/api/tasks").status_code == 200


def test_all_five_modules_contribute_routes(client: TestClient) -> None:
    assert {"activities", "programmes", "staff", "alerts", "reports"} <= endpoint_tags(client)


def test_wiring_is_idempotent_across_repeated_factory_calls() -> None:
    """The test suite builds an app per test; a non-idempotent subscription would silently
    multiply every cross-module side effect."""
    wire_event_handlers()
    wire_event_handlers()
    create_app()

    # the audit sink plus the alerts handler, once each
    assert event_bus.subscriber_count(EventName.ACTIVITY_STATUS_CHANGED) == 2
    assert event_bus.subscriber_count(EventName.ACTIVITY_CREATED) == 1


def test_openapi_schema_is_generated(client: TestClient) -> None:
    """A broken response_model would surface here rather than at runtime."""
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/tasks" in response.json()["paths"]
