"""Distributed task idempotency protection for at-least-once delivery guarantees."""

from __future__ import annotations

import functools
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, TypeVar

import redis
from redis.asyncio import Redis as AsyncRedis

from app.core.config import Settings, get_settings
from app.core.redis import get_sync_redis_client
from app.core.tasks.base import TransientTaskError

logger = logging.getLogger("app.tasks.idempotency")

F = TypeVar("F", bound=Callable[..., Any])

IDEMPOTENCY_PREFIX = "idempotency:task:"


class IdempotencyManager:
    """Manages distributed idempotency locks and cached execution results via Redis."""

    def __init__(
        self,
        sync_client: redis.Redis[Any] | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._sync_client = sync_client

    @property
    def sync_client(self) -> redis.Redis[Any]:
        if self._sync_client is None:
            self._sync_client = get_sync_redis_client(self.settings)
        return self._sync_client

    def _format_key(self, key: str) -> str:
        return f"{IDEMPOTENCY_PREFIX}{key}"

    def acquire(
        self,
        key: str,
        task_id: str,
        lock_ttl: int = 300,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Attempt to acquire idempotency lock for task execution.

        Returns:
            (True, None) if lock was successfully acquired.
            (False, payload) if key already exists (already processing or completed).
        """
        redis_key = self._format_key(key)
        now_str = datetime.now(UTC).isoformat()
        initial_payload = json.dumps(
            {
                "status": "PROCESSING",
                "task_id": task_id,
                "created_at": now_str,
                "result": None,
            }
        )

        acquired = bool(self.sync_client.set(redis_key, initial_payload, ex=lock_ttl, nx=True))
        if acquired:
            return True, None

        raw_existing = self.sync_client.get(redis_key)
        if raw_existing:
            try:
                data = json.loads(str(raw_existing))
                return False, data
            except (json.JSONDecodeError, TypeError):
                pass
        return False, {"status": "PROCESSING", "task_id": "unknown"}

    def complete(
        self,
        key: str,
        result: Any,
        task_id: str,
        result_ttl: int = 86400,
    ) -> None:
        """Store completed execution result under the idempotency key with retention TTL."""
        redis_key = self._format_key(key)
        now_str = datetime.now(UTC).isoformat()
        payload = json.dumps(
            {
                "status": "COMPLETED",
                "task_id": task_id,
                "completed_at": now_str,
                "result": result,
            }
        )
        self.sync_client.set(redis_key, payload, ex=result_ttl)

    def fail(
        self,
        key: str,
        error: str,
        task_id: str,
        ttl: int = 3600,
    ) -> None:
        """Mark task as permanently failed under the idempotency key."""
        redis_key = self._format_key(key)
        now_str = datetime.now(UTC).isoformat()
        payload = json.dumps(
            {
                "status": "FAILED",
                "task_id": task_id,
                "failed_at": now_str,
                "error": error,
            }
        )
        self.sync_client.set(redis_key, payload, ex=ttl)

    def release(self, key: str) -> None:
        """Release lock allowing subsequent retry or invocation."""
        redis_key = self._format_key(key)
        self.sync_client.delete(redis_key)

    @classmethod
    async def acquire_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
        task_id: str,
        lock_ttl: int = 300,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Asynchronously attempt to acquire idempotency lock for FastAPI endpoints."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}"
        now_str = datetime.now(UTC).isoformat()
        initial_payload = json.dumps(
            {
                "status": "PROCESSING",
                "task_id": task_id,
                "created_at": now_str,
                "result": None,
            }
        )
        acquired = bool(await client.set(redis_key, initial_payload, ex=lock_ttl, nx=True))
        if acquired:
            return True, None

        raw = await client.get(redis_key)
        if raw:
            try:
                data = json.loads(str(raw))
                return False, data
            except (json.JSONDecodeError, TypeError):
                pass
        return False, {"status": "PROCESSING", "task_id": "unknown"}

    @classmethod
    async def get_async(
        cls,
        client: AsyncRedis[Any],
        key: str,
    ) -> dict[str, Any] | None:
        """Asynchronously retrieve idempotency payload from Redis."""
        redis_key = f"{IDEMPOTENCY_PREFIX}{key}"
        raw = await client.get(redis_key)
        if raw:
            try:
                return json.loads(str(raw))  # type: ignore[no-any-return]
            except (json.JSONDecodeError, TypeError):
                return None
        return None


def idempotent_task(
    key_param: str = "idempotency_key",
    lock_ttl: int = 300,
    result_ttl: int = 86400,
) -> Callable[[F], F]:
    """Decorator ensuring Celery task execution is idempotent under at-least-once delivery.

    If the task was already completed, returns the cached result.
    If the task is currently processing by another worker, returns a duplicate execution suppression record.
    """

    def decorator(fn: F) -> F:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Extract idempotency key
            idempotency_key = kwargs.get(key_param)
            if not idempotency_key:
                # No key specified; execute standard non-idempotent path
                return fn(*args, **kwargs)

            # Determine task_id if called as bound task method or regular function
            task_id = "standalone"
            if args and hasattr(args[0], "request") and hasattr(args[0].request, "id"):
                task_id = args[0].request.id or "unknown"

            manager = IdempotencyManager()
            acquired, existing = manager.acquire(
                key=str(idempotency_key),
                task_id=task_id,
                lock_ttl=lock_ttl,
            )

            if not acquired and existing:
                if existing.get("status") == "COMPLETED":
                    logger.info(
                        "Idempotent task returning cached result: key=%s, task_id=%s",
                        idempotency_key,
                        task_id,
                    )
                    return existing.get("result")
                if existing.get("status") == "PROCESSING":
                    logger.warning(
                        "Duplicate task execution suppressed (already running): key=%s, owner_task_id=%s",
                        idempotency_key,
                        existing.get("task_id"),
                    )
                    return {
                        "status": "duplicate_execution_suppressed",
                        "idempotency_key": idempotency_key,
                        "original_task_id": existing.get("task_id"),
                    }

            try:
                result = fn(*args, **kwargs)
                manager.complete(
                    key=str(idempotency_key),
                    result=result,
                    task_id=task_id,
                    result_ttl=result_ttl,
                )
                return result
            except TransientTaskError:
                # Release lock so automatic retry can re-acquire
                manager.release(str(idempotency_key))
                raise
            except Exception as exc:
                manager.fail(
                    key=str(idempotency_key),
                    error=str(exc),
                    task_id=task_id,
                )
                raise

        return wrapper  # type: ignore[return-value]

    return decorator
