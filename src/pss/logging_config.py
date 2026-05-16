"""Structlog: konsol (dev) eller JSON (prod / LOG_FORMAT=json)."""

from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog

from pss.config import settings

LogFormat = Literal["console", "json"]


def resolve_log_format() -> LogFormat:
    """Vælg log-format: eksplicit LOG_FORMAT eller auto ud fra ENVIRONMENT."""
    if settings.log_format in ("console", "json"):
        return settings.log_format
    return "json" if settings.is_production else "console"


def configure_logging() -> LogFormat:
    """Konfigurér structlog + stdlib. Returnerer aktivt format."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    log_format = resolve_log_format()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
    ]

    if log_format == "json":
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    # SQLAlchemy: kun WARN i JSON-tilstand; echo på engine styrer stadig dev-SQL
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.WARNING if log_format == "json" else level,
    )
    logging.getLogger("apscheduler").setLevel(level)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    structlog.get_logger(__name__).info(
        "logging_configured",
        log_format=log_format,
        log_level=settings.log_level,
        environment=settings.environment,
    )
    return log_format


__all__ = ["configure_logging", "resolve_log_format"]
