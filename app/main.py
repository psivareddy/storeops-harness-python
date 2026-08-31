"""StoreOps application factory — the composition root.

This is the only place that knows about every module at once. Wiring the event subscriptions
here rather than inside a business module is what keeps the modules mutually ignorant: the
``activities`` service publishes without knowing ``alerts`` exists, and ``alerts`` subscribes
without knowing where the event came from.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI

from app.activities.routes import router as activities_router
from app.alerts.routes import router as alerts_router
from app.alerts.service import alerts_service
from app.programmes.routes import router as programmes_router
from app.reports.routes import router as reports_router
from app.shared.audit import audit_sink
from app.shared.config import Settings, get_settings
from app.shared.errors import register_error_handlers
from app.shared.events import event_bus
from app.shared.logging import configure_logging, get_logger
from app.staff.routes import router as staff_router

logger = get_logger(__name__)

API_VERSION = "0.1.0"


def wire_event_handlers() -> None:
    """Attach the audit sink and every module's event subscribers.

    Idempotent: :meth:`~app.shared.events.EventBus.subscribe` ignores duplicate registrations,
    so calling the factory more than once in a process (as the test suite does) cannot produce
    duplicated side effects.
    """
    audit_sink.attach(event_bus)
    alerts_service.register_event_handlers(event_bus)


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the StoreOps application."""
    resolved = settings if settings is not None else get_settings()
    configure_logging(resolved.log_level)

    application = FastAPI(
        title=resolved.app_name,
        version=API_VERSION,
        description=(
            "Retail store operations management. Five modules (activities, programmes, staff, "
            "alerts, reports), each layered Routes -> Service -> Repository, with cross-module "
            "side effects raised via the shared event bus."
        ),
    )

    register_error_handlers(application)
    wire_event_handlers()

    for router in (
        activities_router,
        programmes_router,
        staff_router,
        alerts_router,
        reports_router,
    ):
        application.include_router(router)

    @application.get("/health", tags=["infrastructure"])
    def health() -> dict[str, Any]:
        """Liveness probe. Used by the container HEALTHCHECK and the CI smoke check."""
        return {
            "status": "ok",
            "app": resolved.app_name,
            "environment": resolved.environment,
            "version": API_VERSION,
        }

    logger.info("%s v%s ready (%s)", resolved.app_name, API_VERSION, resolved.environment)
    return application


app = create_app()
