"""The StoreOps typed error contract.

Every failure raised by a service or a route is an :class:`AppError` carrying the three fields
the contract requires: ``code``, ``message``, and ``status_code``. The capstone brief names the
third field ``statusCode``; that is the *wire* name and is emitted verbatim by
:meth:`AppError.to_payload`, while the Python attribute uses snake_case so it satisfies
pep8-naming (ruff ``N815``).

Prevents **Failure Mode 2** — raw error throws bypassing the typed hierarchy. A raw exception
escaping a service returns an untyped 500 to a store manager with no machine-readable code for
the caller to branch on.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from fastapi.responses import JSONResponse

from app.shared.logging import get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from fastapi import FastAPI, Request

logger = get_logger(__name__)

INTERNAL_ERROR_CODE: Final = "INTERNAL_ERROR"


class AppError(Exception):
    """Base class for every StoreOps domain error.

    Subclasses set ``code`` and ``status_code`` as class attributes so a raise site never has to
    restate them, which is what keeps the codes stable enough for clients to depend on.
    """

    code: str = "APP_ERROR"
    status_code: int = 500

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details: dict[str, Any] = dict(details) if details else {}

    def to_payload(self) -> dict[str, Any]:
        """Render the error in the StoreOps wire format."""
        payload: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
            "statusCode": self.status_code,
        }
        if self.details:
            payload["details"] = self.details
        return payload

    def __repr__(self) -> str:
        return f"{type(self).__name__}(code={self.code!r}, message={self.message!r})"


# --------------------------------------------------------------------------------------
# 404 — entity lookups. One subclass per module so the code identifies the missing entity
# type without the caller parsing the message.
# --------------------------------------------------------------------------------------
class NotFoundError(AppError):
    """An addressed entity does not exist."""

    code = "NOT_FOUND"
    status_code = 404


class TaskNotFoundError(NotFoundError):
    code = "TASK_NOT_FOUND"

    def __init__(self, task_id: str) -> None:
        super().__init__(f"Task '{task_id}' does not exist", details={"taskId": task_id})


class ProjectNotFoundError(NotFoundError):
    code = "PROJECT_NOT_FOUND"

    def __init__(self, project_id: str) -> None:
        super().__init__(
            f"Project '{project_id}' does not exist", details={"projectId": project_id}
        )


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"

    def __init__(self, user_id: str) -> None:
        super().__init__(f"User '{user_id}' does not exist", details={"userId": user_id})


class NotificationNotFoundError(NotFoundError):
    code = "NOTIFICATION_NOT_FOUND"

    def __init__(self, notification_id: str) -> None:
        super().__init__(
            f"Notification '{notification_id}' does not exist",
            details={"notificationId": notification_id},
        )


class StoreNotFoundError(NotFoundError):
    code = "STORE_NOT_FOUND"

    def __init__(self, store_id: str) -> None:
        super().__init__(f"Store '{store_id}' does not exist", details={"storeId": store_id})


# --------------------------------------------------------------------------------------
# 409 / 422 — business rule violations
# --------------------------------------------------------------------------------------
class ValidationError(AppError):
    """Input is structurally valid but violates a business rule."""

    code = "VALIDATION_ERROR"
    status_code = 422


class ConflictError(AppError):
    """The request conflicts with current state."""

    code = "CONFLICT"
    status_code = 409


class InvalidStatusTransitionError(ConflictError):
    """A task status change is not permitted from the current status."""

    code = "INVALID_STATUS_TRANSITION"

    def __init__(self, task_id: str, current: str, requested: str) -> None:
        super().__init__(
            f"Task '{task_id}' cannot move from {current} to {requested}",
            details={"taskId": task_id, "currentStatus": current, "requestedStatus": requested},
        )


class DuplicateMemberError(ConflictError):
    """A staff member is already enrolled on a programme."""

    code = "DUPLICATE_MEMBER"

    def __init__(self, project_id: str, user_id: str) -> None:
        super().__init__(
            f"User '{user_id}' is already a member of project '{project_id}'",
            details={"projectId": project_id, "userId": user_id},
        )


# --------------------------------------------------------------------------------------
# 403 — the read-only reports guarantee, enforced at runtime as well as by contract
# --------------------------------------------------------------------------------------
class ForbiddenWriteError(AppError):
    """A write was attempted from a module that is read-only by contract."""

    code = "FORBIDDEN_WRITE"
    status_code = 403

    def __init__(self, module: str, operation: str) -> None:
        super().__init__(
            f"Module '{module}' is read-only; operation '{operation}' is not permitted",
            details={"module": module, "operation": operation},
        )


# --------------------------------------------------------------------------------------
# FastAPI wiring
# --------------------------------------------------------------------------------------
async def app_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Map an :class:`AppError` to the StoreOps error envelope."""
    if not isinstance(exc, AppError):  # pragma: no cover - FastAPI dispatches by type
        raise exc
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_payload()})


async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler so no bare traceback ever reaches a client.

    Reaching this handler is a defect, not a control path: it means a service raised something
    outside the typed hierarchy, which is exactly Failure Mode 2. It is logged at ``exception``
    level so the harness Monitor can spot it in a run.
    """
    logger.exception("Unhandled non-AppError exception escaped a service", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": INTERNAL_ERROR_CODE,
                "message": "An unexpected internal error occurred",
                "statusCode": 500,
            }
        },
    )


def register_error_handlers(application: FastAPI) -> None:
    """Attach the StoreOps error contract to a FastAPI application."""
    application.add_exception_handler(AppError, app_error_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)
