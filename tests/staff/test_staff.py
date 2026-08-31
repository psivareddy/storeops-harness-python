"""staff is read-only to the rest of StoreOps."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.shared.errors import UserNotFoundError
from app.staff.models import AuthToken, StaffRole
from app.staff.service import StaffService
from tests.conftest import api_endpoints


@pytest.fixture
def service() -> StaffService:
    return StaffService()


def test_get_user_returns_the_addressed_staff_member(service: StaffService) -> None:
    user = service.get_user("user-3")

    assert user.role is StaffRole.DEPARTMENT_LEAD
    assert user.profile.department == "Grocery"
    assert user.store_id == "store-101"


def test_get_user_raises_typed_error_rather_than_returning_none(service: StaffService) -> None:
    with pytest.raises(UserNotFoundError) as caught:
        service.get_user("user-999")

    assert caught.value.code == "USER_NOT_FOUND"
    assert caught.value.status_code == 404
    assert caught.value.details == {"userId": "user-999"}


def test_list_users_filters_by_store_and_role(service: StaffService) -> None:
    assert len(service.list_users()) == 4
    assert {user.store_id for user in service.list_users(store_id="store-101")} == {"store-101"}
    managers = service.list_users(role=StaffRole.STORE_MANAGER)
    assert [user.id for user in managers] == ["user-2"]


def test_department_of_resolves_through_the_profile(service: StaffService) -> None:
    assert service.department_of("user-4") == "Chilled"
    assert service.department_of("user-1") is None  # regional manager has a region, no department


def test_department_of_propagates_user_not_found(service: StaffService) -> None:
    with pytest.raises(UserNotFoundError):
        service.department_of("user-999")


def test_service_exposes_no_write_method() -> None:
    """The read-only-to-siblings guarantee, asserted by introspection so it cannot be relaxed
    without a test failing."""
    forbidden = {"create", "create_user", "update", "update_user", "delete", "delete_user", "save"}
    assert forbidden.isdisjoint(dir(StaffService))


def test_auth_token_validity_window() -> None:
    issued = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)
    token = AuthToken(
        token="tok-1", user_id="user-2", issued_at=issued, expires_at=issued + timedelta(hours=1)
    )

    assert token.is_valid_at(issued) is True
    assert token.is_valid_at(issued + timedelta(minutes=59)) is True
    assert token.is_valid_at(issued + timedelta(hours=1)) is False
    assert token.is_valid_at(issued - timedelta(seconds=1)) is False


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def test_list_users_endpoint_returns_staff(client: TestClient) -> None:
    response = client.get("/api/users")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 4
    assert {user["role"] for user in body} == {
        "REGIONAL_MANAGER",
        "STORE_MANAGER",
        "DEPARTMENT_LEAD",
        "ASSOCIATE",
    }


def test_list_users_endpoint_filters_by_role(client: TestClient) -> None:
    response = client.get("/api/users", params={"role": "ASSOCIATE"})

    assert [user["id"] for user in response.json()] == ["user-4"]


def test_staff_router_exposes_no_write_endpoint(client: TestClient) -> None:
    """Read-only to siblings, and read-only over HTTP too."""
    assert api_endpoints(client, prefix="/api/users") == {("GET", "/api/users")}


def test_write_verbs_against_the_staff_endpoint_are_not_routed(client: TestClient) -> None:
    for verb in ("post", "put", "patch", "delete"):
        response = getattr(client, verb)("/api/users")
        assert response.status_code == 405, f"{verb.upper()} unexpectedly routed"
