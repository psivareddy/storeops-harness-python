"""Configuration is environment-driven, with a safe fallback for malformed values."""

from __future__ import annotations

import pytest

from app.shared.config import (
    DEFAULT_SLA_GRACE_MINUTES,
    Settings,
    get_settings,
)
from app.shared.logging import configure_logging, get_logger


def test_defaults_apply_when_environment_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "STOREOPS_APP_NAME",
        "STOREOPS_ENV",
        "STOREOPS_LOG_LEVEL",
        "STOREOPS_SLA_GRACE_MINUTES",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = get_settings()

    assert settings.app_name == "StoreOps API"
    assert settings.environment == "local"
    assert settings.is_local is True
    assert settings.sla_grace_period_minutes == DEFAULT_SLA_GRACE_MINUTES


def test_environment_overrides_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("STOREOPS_APP_NAME", "StoreOps Staging")
    monkeypatch.setenv("STOREOPS_ENV", "staging")
    monkeypatch.setenv("STOREOPS_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("STOREOPS_SLA_GRACE_MINUTES", "15")

    settings = get_settings()

    assert settings.app_name == "StoreOps Staging"
    assert settings.environment == "staging"
    assert settings.is_local is False
    assert settings.log_level == "DEBUG"
    assert settings.sla_grace_period_minutes == 15


@pytest.mark.parametrize("raw", ["not-a-number", "", "   "])
def test_malformed_grace_period_falls_back_rather_than_crashing_at_boot(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    """A bad environment variable must not take the service down on start-up in a deployed
    environment -- it degrades to the documented default instead."""
    monkeypatch.setenv("STOREOPS_SLA_GRACE_MINUTES", raw)

    assert get_settings().sla_grace_period_minutes == DEFAULT_SLA_GRACE_MINUTES


def test_settings_are_immutable() -> None:
    settings = Settings()

    with pytest.raises((AttributeError, TypeError)):
        settings.environment = "production"  # type: ignore[misc]


@pytest.mark.parametrize("level", ["DEBUG", "info", "WARNING", "nonsense"])
def test_configure_logging_accepts_any_case_and_unknown_levels(level: str) -> None:
    configure_logging(level)

    assert get_logger("app.test").name == "app.test"
