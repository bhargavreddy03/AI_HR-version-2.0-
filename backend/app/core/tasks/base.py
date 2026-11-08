"""Base Celery task class, standardized exception hierarchy, and structured telemetry."""

from __future__ import annotations

import logging
import time
from typing import Any

from celery import Task

logger = logging.getLogger("app.tasks")


class CeleryTaskError(Exception):
    """Base exception for all background Celery task failures."""


class TransientTaskError(CeleryTaskError):
    """Transient task error that should trigger exponential backoff and retry."""


class PermanentTaskError(CeleryTaskError):
    """Permanent task error that must not be retried (e.g., validation, business errors)."""


class BaseTask(Task):  # type: ignore[misc]
    """Base Celery task providing structured logging, telemetry, and security sanitization."""

    abstract = True

    # Field names that must be redacted in logs and telemetry
    SENSITIVE_FIELD_NAMES: frozenset[str] = frozenset(
        {
            "password",
            "secret",
            "token",
            "key",
            "authorization",
            "mfa_secret",
            "pepper",
            "jwt",
            "credential",
            "cookie",
            "api_key",
        }
    )

    @classmethod
    def sanitize_payload(cls, data: Any) -> Any:
        """Recursively redact sensitive fields from arguments and payloads for safe logging."""
        if isinstance(data, dict):
            sanitized: dict[str, Any] = {}
            for k, v in data.items():
                if any(sens in str(k).lower() for sens in cls.SENSITIVE_FIELD_NAMES):
                    sanitized[str(k)] = "******"
                else:
                    sanitized[str(k)] = cls.sanitize_payload(v)
            return sanitized
        if isinstance(data, list | tuple):
            res = [cls.sanitize_payload(item) for item in data]
            return tuple(res) if isinstance(data, tuple) else res
        return data

    def before_start(self, task_id: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> None:
        """Hook called before task execution begins."""
        self._execution_start_time = time.monotonic()
        safe_args = self.sanitize_payload(args)
        safe_kwargs = self.sanitize_payload(kwargs)
        logger.info(
            "Task started: %s [id=%s, queue=%s, args=%s, kwargs=%s]",
            self.name,
            task_id,
            getattr(self.request, "delivery_info", {}).get("routing_key", "default"),
            safe_args,
            safe_kwargs,
        )

    def on_success(
        self,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Hook called after task execution completes successfully."""
        start_time = getattr(self, "_execution_start_time", None)
        duration_ms = (time.monotonic() - start_time) * 1000.0 if start_time is not None else 0.0
        safe_retval = self.sanitize_payload(retval)
        logger.info(
            "Task succeeded: %s [id=%s, duration_ms=%.2f, result=%s]",
            self.name,
            task_id,
            duration_ms,
            safe_retval,
        )

    def on_retry(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Hook called when task is scheduled for retry."""
        retries = getattr(self.request, "retries", 0)
        max_retries = getattr(self, "max_retries", 3)
        logger.warning(
            "Task retrying: %s [id=%s, attempt=%d/%s, error=%s]",
            self.name,
            task_id,
            retries + 1,
            max_retries if max_retries is not None else "inf",
            exc,
        )

    def on_failure(
        self,
        exc: Exception,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Hook called when task fails permanently after retries or due to permanent error."""
        start_time = getattr(self, "_execution_start_time", None)
        duration_ms = (time.monotonic() - start_time) * 1000.0 if start_time is not None else 0.0
        safe_args = self.sanitize_payload(args)
        safe_kwargs = self.sanitize_payload(kwargs)
        logger.error(
            "Task failed: %s [id=%s, duration_ms=%.2f, error_type=%s, error=%s, args=%s, kwargs=%s]",
            self.name,
            task_id,
            duration_ms,
            type(exc).__name__,
            exc,
            safe_args,
            safe_kwargs,
            exc_info=exc,
        )
