from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def setup_logging(level: str | None = None) -> None:
    """Configure structured stdout logging for Docker/Railway."""
    log_level = (level or settings.log_level or "INFO").upper()
    numeric_level = getattr(logging, log_level, logging.INFO)

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=numeric_level,
        force=True,
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(numeric_level),
        cache_logger_on_first_use=True,
    )


def configure_logging(level: str = "INFO") -> None:
    """Backward-compatible alias for older imports."""
    setup_logging(level)


def get_logger(name: str):
    return structlog.get_logger(name)
