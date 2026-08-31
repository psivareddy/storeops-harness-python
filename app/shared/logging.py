"""Logging configuration.

Kept dependency-free (stdlib only) because every other ``app.shared`` module imports it; a
heavier logger here would be paid by the whole application.
"""

from __future__ import annotations

import logging
from typing import Final

LOG_FORMAT: Final = "%(asctime)s %(levelname)-8s %(name)s :: %(message)s"

_LEVELS: Final[dict[str, int]] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def configure_logging(level: str = "INFO") -> None:
    """Configure root logging once, at application start."""
    logging.basicConfig(level=_LEVELS.get(level.upper(), logging.INFO), format=LOG_FORMAT)


def get_logger(name: str) -> logging.Logger:
    """Module-scoped logger."""
    return logging.getLogger(name)
