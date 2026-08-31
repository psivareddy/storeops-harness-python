"""Environment-driven configuration.

Read from the environment rather than a committed file so the same image can be promoted across
environments without a rebuild (see ``DEPLOYMENT.md``). No secret has a default.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

DEFAULT_APP_NAME: Final = "StoreOps API"
DEFAULT_ENVIRONMENT: Final = "local"
DEFAULT_LOG_LEVEL: Final = "INFO"
DEFAULT_SLA_GRACE_MINUTES: Final = 60


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable application settings."""

    app_name: str = DEFAULT_APP_NAME
    environment: str = DEFAULT_ENVIRONMENT
    log_level: str = DEFAULT_LOG_LEVEL
    sla_grace_period_minutes: int = DEFAULT_SLA_GRACE_MINUTES

    @property
    def is_local(self) -> bool:
        return self.environment == DEFAULT_ENVIRONMENT


def _int_from_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_settings() -> Settings:
    """Build settings from the current environment.

    Deliberately uncached so a test can vary the environment without process-global state.
    """
    return Settings(
        app_name=os.getenv("STOREOPS_APP_NAME", DEFAULT_APP_NAME),
        environment=os.getenv("STOREOPS_ENV", DEFAULT_ENVIRONMENT),
        log_level=os.getenv("STOREOPS_LOG_LEVEL", DEFAULT_LOG_LEVEL),
        sla_grace_period_minutes=_int_from_env(
            "STOREOPS_SLA_GRACE_MINUTES", DEFAULT_SLA_GRACE_MINUTES
        ),
    )
