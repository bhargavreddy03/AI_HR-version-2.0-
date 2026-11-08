"""Celery health check and diagnostic probe for Docker containers and orchestration."""

from __future__ import annotations

import logging
import os
import sys
from typing import Any

from app.core.celery_app import celery_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("app.core.celery_health")

EXPECTED_TASK_QUEUES: frozenset[str] = frozenset(
    {
        "default",
        "document_processing",
        "resume_parsing",
        "embedding_generation",
        "candidate_matching",
        "notifications",
        "reporting",
    }
)


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


def check_celery_queues_health(timeout: float = 3.0) -> bool:
    """Inspect active workers to confirm configured task queues are actively consumed."""
    try:
        inspect = celery_app.control.inspect(timeout=timeout)
        active_queues = inspect.active_queues()
        if not active_queues:
            logger.warning("No active queues reported by Celery workers")
            return False

        all_queues: set[str] = set()
        for queues in active_queues.values():
            if isinstance(queues, list):
                for q in queues:
                    if isinstance(q, dict) and "name" in q:
                        all_queues.add(q["name"])

        missing_queues = EXPECTED_TASK_QUEUES - all_queues
        if missing_queues:
            logger.warning(
                "Celery workers missing expected queues: %s (active: %s)",
                missing_queues,
                all_queues,
            )
            return False

        logger.info("All %d configured Celery queues actively consumed", len(EXPECTED_TASK_QUEUES))
        return True
    except Exception as exc:
        logger.error("Celery queue health probe failed: %s", exc)
        return False


def run_health_probe() -> bool:
    """Run container health probe verifying broker reachability and worker responsiveness."""
    broker_ok = check_celery_broker_health()
    if not broker_ok:
        return False

    # Check worker responsiveness when --workers is passed or CELERY_HEALTH_CHECK_WORKERS=true
    check_workers = "--workers" in sys.argv or os.getenv(
        "CELERY_HEALTH_CHECK_WORKERS", ""
    ).lower() in (
        "true",
        "1",
        "yes",
    )
    if check_workers:
        if not check_celery_workers_health():
            return False

    # Check queues when --queues is explicitly passed
    if "--queues" in sys.argv:
        if not check_celery_queues_health():
            return False

    return True


if __name__ == "__main__":
    if run_health_probe():
        sys.exit(0)
    sys.exit(1)
