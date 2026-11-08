"""Celery health check and diagnostic probe for Docker containers and orchestration."""

from __future__ import annotations

import logging
import sys
from typing import Any

from app.core.celery_app import celery_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.core.celery_health")


def check_celery_broker_health(timeout: float = 3.0) -> bool:
    """Verify live connectivity against the configured Celery Redis message broker."""
    try:
        with celery_app.connection_for_read() as conn:
            conn.ensure_connection(max_retries=1, interval_start=0.2)
            # Verify basic transport ping
            transport: Any = getattr(conn, "default_channel", None)
            if transport and hasattr(transport, "client"):
                transport.client.ping()
        return True
    except Exception as exc:
        logger.error("Celery broker health probe failed: %s", exc)
        return False


def check_celery_workers_health(timeout: float = 3.0) -> bool:
    """Inspect active workers responding to ping via broadcast."""
    try:
        inspect = celery_app.control.inspect(timeout=timeout)
        ping_response = inspect.ping()
        if ping_response and any(ping_response.values()):
            logger.info("Celery active workers responding: %s", list(ping_response.keys()))
            return True
        logger.warning("No Celery workers responded to inspect ping")
        return False
    except Exception as exc:
        logger.error("Celery worker inspect ping failed: %s", exc)
        return False


def run_health_probe() -> bool:
    """Run container health probe verifying broker reachability."""
    broker_ok = check_celery_broker_health()
    if not broker_ok:
        return False
    # If explicitly requested with --workers, also verify responsive workers
    if "--workers" in sys.argv:
        return check_celery_workers_health()
    return True


if __name__ == "__main__":
    if run_health_probe():
        sys.exit(0)
    sys.exit(1)
