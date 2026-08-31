"""staff business logic.

The staff module is read-only to the rest of StoreOps: :meth:`StaffService.get_user` and
:meth:`StaffService.list_users` are the only surface siblings may use, and there is deliberately
no write method for a sibling to reach for.
"""

from __future__ import annotations

from app.shared.errors import UserNotFoundError
from app.shared.logging import get_logger
from app.staff.models import StaffRole, User
from app.staff.repository import UserRepository, user_repository

logger = get_logger(__name__)


class StaffService:
    """Read operations for store staff."""

    def __init__(self, repository: UserRepository | None = None) -> None:
        self._repository = repository if repository is not None else user_repository

    def list_users(
        self, *, store_id: str | None = None, role: StaffRole | None = None
    ) -> list[User]:
        return self._repository.list_all(store_id=store_id, role=role)

    def get_user(self, user_id: str) -> User:
        """Return a user or raise :class:`UserNotFoundError`.

        This is the cross-module read entry point. ``programmes`` calls it to validate an
        enrolment and ``reports`` calls it to resolve department names.
        """
        user = self._repository.get(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user

    def users_for_store(self, store_id: str) -> list[User]:
        return self._repository.list_all(store_id=store_id)

    def department_of(self, user_id: str) -> str | None:
        """Resolve a user's department, or ``None`` when unassigned."""
        return self.get_user(user_id).profile.department


staff_service = StaffService()
