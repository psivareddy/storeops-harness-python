"""alerts HTTP layer: validation and delegation only.

Reads only, by design. Notifications are created by the event handler in ``service.py``, so
there is no endpoint another module could call to manufacture an alert directly.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query

from app.alerts.models import AlertType, Notification
from app.alerts.service import alerts_service

router = APIRouter(prefix="/api/notifications", tags=["alerts"])


@router.get("", response_model=list[Notification])
def list_notifications(
    recipient_id: Annotated[str | None, Query(description="Filter by recipient")] = None,
    alert_type: Annotated[AlertType | None, Query(description="Filter by alert type")] = None,
    store_id: Annotated[str | None, Query(description="Filter by store")] = None,
) -> list[Notification]:
    """List operational alerts, optionally filtered by recipient, type and store."""
    return alerts_service.list_notifications(
        recipient_id=recipient_id, alert_type=alert_type, store_id=store_id
    )
