"""Foundational system tasks for health verification, reliability testing, and routing proof."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.celery_app import celery_app
from app.core.tasks.base import BaseTask, PermanentTaskError, TransientTaskError
from app.core.tasks.idempotency import idempotent_task

logger = logging.getLogger("app.tasks.system")


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.core.tasks.system.system_ping",
)
@idempotent_task(key_param="idempotency_key", lock_ttl=60, result_ttl=3600)
def system_ping(
    self: Any,
    message: str = "ping",
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Lightweight system ping task validating worker execution, Redis broker, and result backend."""
    now_utc = datetime.now(UTC).isoformat()
    return {
        "status": "pong",
        "message": message,
        "task_id": self.request.id,
        "timestamp": now_utc,
        "queue": getattr(self.request, "delivery_info", {}).get("routing_key", "default"),
        "idempotency_key": idempotency_key,
    }


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.core.tasks.system.sample_transient_retry",
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    max_retries=3,
)
def sample_transient_retry(
    self: Any,
    fail_until_attempt: int = 2,
    payload: str = "sample",
) -> dict[str, Any]:
    """Sample task demonstrating automatic retry for transient errors with exponential backoff and jitter."""
    current_attempt = getattr(self.request, "retries", 0) + 1
    if current_attempt < fail_until_attempt:
        logger.warning(
            "Transient failure simulation: attempt %d < %d",
            current_attempt,
            fail_until_attempt,
        )
        raise TransientTaskError(
            f"Transient network blip on attempt {current_attempt} (retrying up to {fail_until_attempt})"
        )

    return {
        "status": "success",
        "attempts_required": current_attempt,
        "payload": payload,
        "task_id": self.request.id,
    }


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.core.tasks.system.sample_permanent_failure",
    max_retries=0,
)
def sample_permanent_failure(self: Any, error_message: str = "Validation failed") -> None:
    """Sample task demonstrating permanent error rejection that must never be retried."""
    raise PermanentTaskError(f"Permanent business validation error: {error_message}")


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.core.tasks.system.sample_idempotent_task",
)
@idempotent_task(key_param="idempotency_key", lock_ttl=60, result_ttl=3600)
def sample_idempotent_task(
    self: Any,
    value: int,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Sample task demonstrating idempotency protection against duplicate execution."""
    return {
        "status": "processed",
        "value": value,
        "computed": value * 2,
        "idempotency_key": idempotency_key,
        "task_id": self.request.id,
    }
