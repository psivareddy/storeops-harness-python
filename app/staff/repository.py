"""staff data access. In-memory; read-only surface, since no module may write staff records."""

from __future__ import annotations

from datetime import UTC, datetime

from app.staff.models import StaffRole, User, UserProfile

_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _seed_users() -> list[User]:
    return [
        User(
            id="user-1",
            email="rhian.regional@example.com",
            role=StaffRole.REGIONAL_MANAGER,
            store_id="store-101",
            profile=UserProfile(display_name="Rhian Ellis", region="North West"),
            created_at=_NOW,
        ),
        User(
            id="user-2",
            email="sam.storemanager@example.com",
            role=StaffRole.STORE_MANAGER,
            store_id="store-101",
            profile=UserProfile(display_name="Sam Okafor", department="Store Office"),
            created_at=_NOW,
        ),
        User(
            id="user-3",
            email="dana.deptlead@example.com",
            role=StaffRole.DEPARTMENT_LEAD,
            store_id="store-101",
            profile=UserProfile(display_name="Dana Whitfield", department="Grocery"),
            created_at=_NOW,
        ),
        User(
            id="user-4",
            email="ade.associate@example.com",
            role=StaffRole.ASSOCIATE,
            store_id="store-102",
            profile=UserProfile(display_name="Ade Balogun", department="Chilled"),
            created_at=_NOW,
        ),
    ]


class UserRepository:
    """In-memory staff store keyed by user id."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self.reset()

    def reset(self) -> None:
        self._users = {user.id: user for user in _seed_users()}

    def list_all(self, *, store_id: str | None = None, role: StaffRole | None = None) -> list[User]:
        users = list(self._users.values())
        if store_id is not None:
            users = [user for user in users if user.store_id == store_id]
        if role is not None:
            users = [user for user in users if user.role is role]
        return sorted(users, key=lambda user: user.id)

    def get(self, user_id: str) -> User | None:
        return self._users.get(user_id)

    def count(self) -> int:
        return len(self._users)


user_repository = UserRepository()
