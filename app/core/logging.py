from __future__ import annotations

import logging
import sys

import structlog

from app.core.config import settings


def setup_logging(level: str | None = None) -> None:
    """
    Configure application logging.

    main.py imports this function directly, so it must exist.
    Logs are written to stdout, which is the correct destination for Railway/Docker.
    """
    log_level = (level or settings.log_level or "INFO").upper()

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level, logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level, logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )


def configure_logging(level: str = "INFO") -> None:
    """
    Backward-compatible alias.

    Some modules may still call configure_logging(), while main.py calls setup_logging().
    Both should work.
    """
    setup_logging(level)


def get_logger(name: str):
    return structlog.get_logger(name)
