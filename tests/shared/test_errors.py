"""The error contract: every failure carries code, message and statusCode."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.shared.errors import (
    AppError,
    ConflictError,
    DuplicateMemberError,
    ForbiddenWriteError,
    InvalidStatusTransitionError,
    NotFoundError,
    NotificationNotFoundError,
    ProjectNotFoundError,
    StoreNotFoundError,
    TaskNotFoundError,
    UserNotFoundError,
    ValidationError,
    register_error_handlers,
)

ALL_ERROR_TYPES = [
    AppError,
    NotFoundError,
    TaskNotFoundError,
    ProjectNotFoundError,
    UserNotFoundError,
    NotificationNotFoundError,
    StoreNotFoundError,
    ValidationError,
    ConflictError,
    InvalidStatusTransitionError,
    DuplicateMemberError,
    ForbiddenWriteError,
]


@pytest.mark.parametrize("error_type", ALL_ERROR_TYPES)
def test_every_error_declares_a_non_default_contract(error_type: type[AppError]) -> None:
    """Each subclass must set ``code`` and ``status_code`` as class attributes so a raise site
    never restates them and client-facing codes stay stable."""
    assert isinstance(error_type.code, str)
    assert error_type.code
    assert 400 <= error_type.status_code <= 599 or error_type is AppError


def test_task_not_found_carries_code_status_and_identifying_details() -> None:
    error = TaskNotFoundError("task-42")

    assert error.code == "TASK_NOT_FOUND"
    assert error.status_code == 404
    assert error.details == {"taskId": "task-42"}
    assert "task-42" in error.message


def test_invalid_status_transition_names_both_statuses() -> None:
    error = InvalidStatusTransitionError("task-4", "DONE", "TODO")

    assert error.code == "INVALID_STATUS_TRANSITION"
    assert error.status_code == 409
    assert error.details == {
        "taskId": "task-4",
        "currentStatus": "DONE",
        "requestedStatus": "TODO",
    }


def test_to_payload_emits_the_wire_field_name_statuscode() -> None:
    """The Python attribute is snake_case for pep8-naming; the wire contract the capstone brief
    specifies is ``statusCode``. Both must be true at once."""
    payload = TaskNotFoundError("task-1").to_payload()

    assert payload["statusCode"] == 404
    assert payload["code"] == "TASK_NOT_FOUND"
    assert "status_code" not in payload
    assert payload["details"] == {"taskId": "task-1"}


def test_to_payload_omits_details_when_empty() -> None:
    payload = AppError("something went wrong").to_payload()

    assert "details" not in payload
    assert payload == {"code": "APP_ERROR", "message": "something went wrong", "statusCode": 500}


def test_forbidden_write_error_names_module_and_operation() -> None:
    error = ForbiddenWriteError("reports", "create_report")

    assert error.code == "FORBIDDEN_WRITE"
    assert error.status_code == 403
    assert error.details == {"module": "reports", "operation": "create_report"}


def test_duplicate_member_error_contract() -> None:
    error = DuplicateMemberError("project-1", "user-2")

    assert error.code == "DUPLICATE_MEMBER"
    assert error.status_code == 409
    assert error.details == {"projectId": "project-1", "userId": "user-2"}


def test_repr_includes_code_and_message_for_log_readability() -> None:
    assert "TASK_NOT_FOUND" in repr(TaskNotFoundError("task-1"))


def test_subclass_hierarchy_allows_catching_by_family() -> None:
    """Catching ``NotFoundError`` must catch every entity-specific 404, so a caller can handle a
    family without enumerating codes."""
    assert isinstance(TaskNotFoundError("t"), NotFoundError)
    assert isinstance(InvalidStatusTransitionError("t", "DONE", "TODO"), ConflictError)
    assert isinstance(StoreNotFoundError("s"), AppError)


# ---------------------------------------------------------------------------
# Handler wiring
# ---------------------------------------------------------------------------
def _app_that_raises(exc: Exception) -> FastAPI:
    application = FastAPI()
    register_error_handlers(application)

    @application.get("/boom")
    def boom() -> None:
        raise exc

    return application


def test_handler_maps_app_error_to_the_storeops_envelope() -> None:
    client = TestClient(_app_that_raises(TaskNotFoundError("task-7")))

    response = client.get("/boom")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "TASK_NOT_FOUND",
            "message": "Task 'task-7' does not exist",
            "statusCode": 404,
            "details": {"taskId": "task-7"},
        }
    }


def test_handler_uses_the_subclass_status_code_not_the_base_500() -> None:
    client = TestClient(_app_that_raises(ValidationError("bad input")))

    response = client.get("/boom")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_unhandled_exception_is_converted_to_the_envelope_without_leaking_detail() -> None:
    """Reaching this path is Failure Mode 2. The response must still be a typed envelope, and
    must not leak the original message to the client."""
    client = TestClient(
        _app_that_raises(RuntimeError("connection string user=admin password=hunter2")),
        raise_server_exceptions=False,
    )

    response = client.get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text
