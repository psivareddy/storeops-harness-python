"""staff domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class StaffRole(StrEnum):
    REGIONAL_MANAGER = "REGIONAL_MANAGER"
    STORE_MANAGER = "STORE_MANAGER"
    DEPARTMENT_LEAD = "DEPARTMENT_LEAD"
    ASSOCIATE = "ASSOCIATE"


class UserProfile(BaseModel):
    """Non-identifying profile detail, separated so it can be returned without contact data."""

    model_config = ConfigDict(frozen=True)

    display_name: str
    department: str | None = None
    region: str | None = None


class User(BaseModel):
    """A member of store staff."""

    model_config = ConfigDict(frozen=True)

    id: str
    email: str
    role: StaffRole
    store_id: str
    profile: UserProfile
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AuthToken(BaseModel):
    """An issued bearer token.

    Modelled for completeness of the staff domain; issuance is out of scope for the baseline and
    is not exposed by any route.
    """

    model_config = ConfigDict(frozen=True)

    token: str
    user_id: str
    issued_at: datetime
    expires_at: datetime

    def is_valid_at(self, moment: datetime) -> bool:
        return self.issued_at <= moment < self.expires_at
