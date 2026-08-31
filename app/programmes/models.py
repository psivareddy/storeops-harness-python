"""programmes domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class ProjectRole(StrEnum):
    STORE_MANAGER = "STORE_MANAGER"
    DEPARTMENT_LEAD = "DEPARTMENT_LEAD"
    ASSOCIATE = "ASSOCIATE"


class ProjectStatus(StrEnum):
    PLANNED = "PLANNED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class ProjectMember(BaseModel):
    """A staff member enrolled on a programme, with the role they hold on it."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    role: ProjectRole
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Project(BaseModel):
    """A store programme."""

    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    store_id: str
    description: str = ""
    status: ProjectStatus = ProjectStatus.PLANNED
    members: tuple[ProjectMember, ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def has_member(self, user_id: str) -> bool:
        return any(member.user_id == user_id for member in self.members)


class ProjectMemberCreate(BaseModel):
    """Route-layer input schema for enrolling a staff member on a programme."""

    user_id: str = Field(min_length=1)
    role: ProjectRole
