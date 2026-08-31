"""programmes business rules, including the permitted cross-module read.

Enrolment validates the staff member through :class:`StaffService` -- the sibling module's
*service* layer. If that call were replaced by a ``UserRepository`` import, ``lint-imports``
would break the ``programmes-no-cross-module-repository`` contract (HG-1).
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.programmes.models import ProjectMemberCreate, ProjectRole, ProjectStatus
from app.programmes.service import ProgrammesService
from app.shared.audit import AuditSink
from app.shared.errors import (
    DuplicateMemberError,
    ProjectNotFoundError,
    UserNotFoundError,
    ValidationError,
)
from app.shared.events import EventBus, EventName


@pytest.fixture
def bus() -> EventBus:
    return EventBus()


@pytest.fixture
def audit(bus: EventBus) -> AuditSink:
    sink = AuditSink()
    sink.attach(bus)
    return sink


@pytest.fixture
def service(bus: EventBus) -> ProgrammesService:
    return ProgrammesService(bus=bus)


def test_add_member_enrols_publishes_one_event_and_audits_once(
    service: ProgrammesService, bus: EventBus, audit: AuditSink
) -> None:
    before = service.get_project("project-1")
    assert before.has_member("user-4") is False

    updated = service.add_member(
        "project-1", ProjectMemberCreate(user_id="user-4", role=ProjectRole.ASSOCIATE)
    )

    # resulting state
    assert updated.has_member("user-4") is True
    assert len(updated.members) == len(before.members) + 1
    assert service.get_project("project-1").has_member("user-4") is True
    enrolled = next(member for member in updated.members if member.user_id == "user-4")
    assert enrolled.role is ProjectRole.ASSOCIATE

    # exactly one event and one audit entry
    events = bus.published_of(EventName.PROGRAMME_MEMBER_ADDED)
    assert len(events) == 1
    assert events[0].payload == {
        "projectId": "project-1",
        "storeId": "store-101",
        "userId": "user-4",
        "role": "ASSOCIATE",
    }
    assert audit.count_for(EventName.PROGRAMME_MEMBER_ADDED) == 1


def test_unknown_project_raises_project_not_found_and_publishes_nothing(
    service: ProgrammesService, bus: EventBus
) -> None:
    with pytest.raises(ProjectNotFoundError) as caught:
        service.add_member(
            "project-999", ProjectMemberCreate(user_id="user-4", role=ProjectRole.ASSOCIATE)
        )

    assert caught.value.code == "PROJECT_NOT_FOUND"
    assert caught.value.status_code == 404
    assert len(bus.published) == 0


def test_unknown_user_surfaces_the_staff_modules_error_code(
    service: ProgrammesService, bus: EventBus
) -> None:
    """The error originates in the staff service and propagates unchanged, which is what makes
    the cross-module read authoritative rather than duplicated."""
    with pytest.raises(UserNotFoundError) as caught:
        service.add_member(
            "project-1", ProjectMemberCreate(user_id="user-999", role=ProjectRole.ASSOCIATE)
        )

    assert caught.value.code == "USER_NOT_FOUND"
    assert caught.value.details == {"userId": "user-999"}
    assert service.get_project("project-1").has_member("user-999") is False
    assert len(bus.published) == 0


def test_closed_programme_rejects_enrolment_and_publishes_nothing(
    service: ProgrammesService, bus: EventBus
) -> None:
    closed = service.get_project("project-3")
    assert closed.status is ProjectStatus.CLOSED

    with pytest.raises(ValidationError) as caught:
        service.add_member(
            "project-3", ProjectMemberCreate(user_id="user-2", role=ProjectRole.STORE_MANAGER)
        )

    assert caught.value.code == "VALIDATION_ERROR"
    assert caught.value.status_code == 422
    assert len(service.get_project("project-3").members) == len(closed.members)
    assert len(bus.published) == 0


def test_duplicate_enrolment_is_rejected_and_publishes_nothing(
    service: ProgrammesService, bus: EventBus
) -> None:
    with pytest.raises(DuplicateMemberError) as caught:
        service.add_member(
            "project-1", ProjectMemberCreate(user_id="user-2", role=ProjectRole.ASSOCIATE)
        )

    assert caught.value.code == "DUPLICATE_MEMBER"
    assert caught.value.status_code == 409
    assert len(service.get_project("project-1").members) == 2
    assert len(bus.published) == 0


def test_list_projects_filters_by_store(service: ProgrammesService) -> None:
    assert [project.id for project in service.list_projects(store_id="store-102")] == ["project-3"]
    assert len(service.list_projects()) == 3


def test_projects_for_store_backs_the_reports_aggregation(service: ProgrammesService) -> None:
    assert len(service.projects_for_store("store-101")) == 2


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------
def test_list_projects_endpoint_returns_members(client: TestClient) -> None:
    response = client.get("/api/projects")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 3
    project_1 = next(item for item in body if item["id"] == "project-1")
    assert len(project_1["members"]) == 2


def test_add_member_endpoint_returns_201_and_the_updated_programme(client: TestClient) -> None:
    response = client.post(
        "/api/projects/project-2/members", json={"user_id": "user-3", "role": "DEPARTMENT_LEAD"}
    )

    assert response.status_code == 201
    assert "user-3" in {member["user_id"] for member in response.json()["members"]}

    listed = client.get("/api/projects").json()
    project_2 = next(item for item in listed if item["id"] == "project-2")
    assert len(project_2["members"]) == 2


def test_add_member_endpoint_propagates_the_typed_error_envelope(client: TestClient) -> None:
    response = client.post(
        "/api/projects/project-3/members", json={"user_id": "user-3", "role": "ASSOCIATE"}
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
