"""alerts data access. In-memory; no business rules, no external calls."""

from __future__ import annotations

from datetime import UTC, datetime

from app.alerts.models import (
    AlertType,
    Notification,
    NotificationChannel,
    NotificationStatus,
)

_NOW = datetime(2026, 8, 31, 8, 0, tzinfo=UTC)


def _seed_notifications() -> list[Notification]:
    return [
        Notification(
            id="notification-1",
            alert_type=AlertType.INVENTORY,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.SENT,
            recipient_id="user-3",
            message="Beverage aisle stock below threshold",
            store_id="store-101",
            subject_task_id="task-1",
            created_at=_NOW,
        ),
        Notification(
            id="notification-2",
            alert_type=AlertType.SLA_BREACH,
            channel=NotificationChannel.EMAIL,
            status=NotificationStatus.SENT,
            recipient_id="user-2",
            message="Chilled cabinet audit is past its due date",
            store_id="store-101",
            subject_task_id="task-3",
            created_at=_NOW,
        ),
    ]


class NotificationRepository:
    """In-memory notification store keyed by notification id."""

    def __init__(self) -> None:
        self._notifications: dict[str, Notification] = {}
        self.reset()

    def reset(self) -> None:
        self._notifications = {item.id: item for item in _seed_notifications()}

    def list_all(
        self,
        *,
        recipient_id: str | None = None,
        alert_type: AlertType | None = None,
        store_id: str | None = None,
    ) -> list[Notification]:
        items = list(self._notifications.values())
        if recipient_id is not None:
            items = [item for item in items if item.recipient_id == recipient_id]
        if alert_type is not None:
            items = [item for item in items if item.alert_type is alert_type]
        if store_id is not None:
            items = [item for item in items if item.store_id == store_id]
        return sorted(items, key=lambda item: item.id)

    def get(self, notification_id: str) -> Notification | None:
        return self._notifications.get(notification_id)

    def add(self, notification: Notification) -> Notification:
        self._notifications[notification.id] = notification
        return notification

    def next_id(self) -> str:
        return f"notification-{len(self._notifications) + 1}"

    def count(self) -> int:
        return len(self._notifications)


notification_repository = NotificationRepository()
