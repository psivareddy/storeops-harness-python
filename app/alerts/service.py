"""alerts business logic — an event-driven module.

This service is the consuming half of the event-bus rule. When an activity is blocked, the
``activities`` module publishes ``ACTIVITY_STATUS_CHANGED``; this module reacts by creating an
``ESCALATION`` notification through **its own** repository.

Contrast with the failure mode this prevents (**Failure Mode 4**): had ``activities`` imported
``app.alerts.repository`` and written the notification itself, the alert would exist but no event
would have been published, so the audit sink would hold no record of it and no second consumer
could ever be added without editing the activities service.
"""

from __future__ import annotations

from app.alerts.models import (
    AlertType,
    Notification,
    NotificationChannel,
    NotificationStatus,
)
from app.alerts.repository import NotificationRepository, notification_repository
from app.shared.errors import NotificationNotFoundError
from app.shared.events import Event, EventBus, EventName, event_bus
from app.shared.logging import get_logger

logger = get_logger(__name__)

#: The task status that triggers an escalation alert.
_ESCALATION_TRIGGER_STATUS = "BLOCKED"


class AlertsService:
    """Read operations plus event-driven notification creation."""

    def __init__(
        self, repository: NotificationRepository | None = None, bus: EventBus | None = None
    ) -> None:
        self._repository = repository if repository is not None else notification_repository
        self._bus = bus if bus is not None else event_bus

    # -- reads ------------------------------------------------------------------
    def list_notifications(
        self,
        *,
        recipient_id: str | None = None,
        alert_type: AlertType | None = None,
        store_id: str | None = None,
    ) -> list[Notification]:
        return self._repository.list_all(
            recipient_id=recipient_id, alert_type=alert_type, store_id=store_id
        )

    def get_notification(self, notification_id: str) -> Notification:
        notification = self._repository.get(notification_id)
        if notification is None:
            raise NotificationNotFoundError(notification_id)
        return notification

    def notifications_for_task(self, task_id: str) -> list[Notification]:
        return [
            item for item in self._repository.list_all() if item.subject_task_id == task_id
        ]

    # -- event handling ---------------------------------------------------------
    def register_event_handlers(self, bus: EventBus | None = None) -> None:
        """Subscribe this module's handlers. Idempotent -- see :meth:`EventBus.subscribe`."""
        target = bus if bus is not None else self._bus
        target.subscribe(EventName.ACTIVITY_STATUS_CHANGED, self.handle_activity_status_changed)

    def handle_activity_status_changed(self, event: Event) -> None:
        """Create an ``ESCALATION`` notification when an activity becomes blocked.

        A blocked activity is the operational signal that someone needs to intervene, so the
        assigned staff member is alerted. Any other transition is not an escalation and creates
        no notification -- the handler must be safe to invoke for every status change.
        """
        new_status = event.payload.get("newStatus")
        if new_status != _ESCALATION_TRIGGER_STATUS:
            return

        recipient_id = event.payload.get("assigneeId")
        if not isinstance(recipient_id, str) or not recipient_id:
            logger.warning(
                "ACTIVITY_STATUS_CHANGED for task %s has no assignee; no alert raised",
                event.payload.get("taskId"),
            )
            return

        task_id = event.payload.get("taskId")
        store_id = event.payload.get("storeId")
        notification = Notification(
            id=self._repository.next_id(),
            alert_type=AlertType.ESCALATION,
            channel=NotificationChannel.IN_APP,
            status=NotificationStatus.PENDING,
            recipient_id=recipient_id,
            message=f"Activity {task_id} is blocked and needs attention",
            store_id=store_id if isinstance(store_id, str) else "unknown",
            subject_task_id=task_id if isinstance(task_id, str) else None,
        )
        self._repository.add(notification)
        logger.info("Escalation alert %s raised for task %s", notification.id, task_id)


alerts_service = AlertsService()
