"""alerts domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class AlertType(StrEnum):
    INVENTORY = "INVENTORY"
    SLA_BREACH = "SLA_BREACH"
    SHIFT_HANDOVER = "SHIFT_HANDOVER"
    ESCALATION = "ESCALATION"


class NotificationChannel(StrEnum):
    IN_APP = "IN_APP"
    EMAIL = "EMAIL"


class NotificationStatus(StrEnum):
    PENDING = "PENDING"
    SENT = "SENT"
    READ = "READ"
    FAILED = "FAILED"


class Notification(BaseModel):
    """An operational alert delivered to a member of store staff.

    ``subject_task_id`` holds a task identifier as an opaque string. It is deliberately not a
    ``Task`` reference: typing it as the activities entity would require importing that module
    and would couple alerts to the activities schema.
    """

    model_config = ConfigDict(frozen=True)

    id: str
    alert_type: AlertType
    channel: NotificationChannel
    status: NotificationStatus
    recipient_id: str
    message: str
    store_id: str
    subject_task_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
