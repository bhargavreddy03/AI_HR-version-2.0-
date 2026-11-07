"""Structured logging configuration with correlation ID tracking."""

import logging
import sys

from app.core.config import get_settings
from app.core.middleware import CorrelationIdFilter


def setup_logging() -> None:
    """Configure system-wide structured logging with correlation ID propagation."""
    settings = get_settings()

    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    log_format = "%(asctime)s | %(levelname)-8s | [%(correlation_id)s] | %(name)s:%(funcName)s:%(lineno)d - %(message)s"

    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(CorrelationIdFilter())

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[handler],
        force=True,
    )

    # Silence overly verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(
        logging.INFO if settings.DEBUG else logging.WARNING
    )
    logging.getLogger("asyncio").setLevel(logging.WARNING)
