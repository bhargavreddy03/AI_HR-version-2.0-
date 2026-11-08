"""Reusable service for asynchronous background task dispatching, status querying, and result retrieval."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from celery import Task
from celery.result import AsyncResult
from pydantic import BaseModel, Field
from redis.asyncio import Redis as AsyncRedis

from app.core.celery_app import celery_app
from app.core.errors import ServiceUnavailableException
from app.core.tasks.idempotency import IDEMPOTENCY_PREFIX, IdempotencyManager

logger = logging.getLogger("app.services.task_service")

TASK_META_PREFIX = "task:meta:"


class TaskSubmissionResult(BaseModel):
    """Result of dispatching a background task."""

    task_id: str = Field(description="Unique Celery task identifier")
    status: str = Field(description="Initial task status (e.g. PENDING, SUBMITTED)")
    queue: str = Field(description="Destination Celery queue")
    duplicate: bool = Field(
        default=False, description="True if task was already submitted or cached"
    )


class TaskStatusResult(BaseModel):
    """Current execution status and telemetry for a background task."""

    task_id: str = Field(description="Unique Celery task identifier")
    status: str = Field(
        description="Current task status (PENDING, STARTED, SUCCESS, FAILURE, RETRY, REVOKED)"
    )
    ready: bool = Field(description="Whether the task has completed execution")
    successful: bool | None = Field(
        default=None, description="True if finished with SUCCESS, False if FAILURE"
    )
    error: str | None = Field(default=None, description="Sanitized error description if failed")
    result: Any | None = Field(
        default=None, description="Task return value if completed successfully"
    )


class TaskService:
    """Service providing safe, non-blocking Celery task interactions from FastAPI."""

    def __init__(self, app_celery: Any = None) -> None:
        self.celery = app_celery or celery_app

    async def submit_task(
        self,
        task: Task | str,
        args: tuple[Any, ...] = (),
        kwargs: dict[str, Any] | None = None,
        queue: str | None = None,
        countdown: int | None = None,
        idempotency_key: str | None = None,
        tenant_id: UUID | str | None = None,
        user_id: UUID | str | None = None,
        redis_client: AsyncRedis[Any] | None = None,
    ) -> TaskSubmissionResult:
        """Submit a background task for asynchronous execution with atomic idempotency and metadata lifecycle."""
        kw = dict(kwargs) if kwargs else {}
        target_queue = queue or "default"
        assigned_task_id = str(uuid.uuid4())
        meta_key = f"{TASK_META_PREFIX}{assigned_task_id}"

        # 1. Atomic Idempotency Registration
        if idempotency_key:
            if redis_client is None:
                raise ServiceUnavailableException(
                    "Idempotency service unavailable. Reliable task idempotency cannot be guaranteed.",
                    error_code="IDEMPOTENCY_UNAVAILABLE",
                )
            kw["idempotency_key"] = idempotency_key

            registered, existing = await IdempotencyManager.register_submission_async(
                client=redis_client,
                key=idempotency_key,
                task_id=assigned_task_id,
                lock_ttl=300,
            )
            if not registered and existing:
                existing_task_id = str(existing.get("task_id", "cached"))
                existing_status = str(existing.get("status", "PROCESSING"))
                logger.info(
                    "Duplicate task submission suppressed: key=%s, existing_id=%s, status=%s",
                    idempotency_key,
                    existing_task_id,
                    existing_status,
                )
                return TaskSubmissionResult(
                    task_id=existing_task_id,
                    status=existing_status,
                    queue=target_queue,
                    duplicate=True,
                )

        # 2. Required Ownership Metadata Persistence
        if tenant_id or user_id or idempotency_key:
            if redis_client is None:
                if idempotency_key:
                    raise ServiceUnavailableException(
                        "Redis service unavailable to store task metadata.",
                        error_code="REDIS_UNAVAILABLE",
                    )
            else:
                meta_payload = json.dumps(
                    {
                        "task_id": assigned_task_id,
                        "tenant_id": str(tenant_id) if tenant_id else None,
                        "user_id": str(user_id) if user_id else None,
                        "queue": target_queue,
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                )
                try:
                    await redis_client.set(meta_key, meta_payload, ex=86400)
                except Exception as meta_exc:
                    # Clean up registered idempotency record if metadata cannot be persisted
                    if idempotency_key and redis_client is not None:
                        try:
                            await redis_client.delete(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")
                        except Exception:
                            pass
                    logger.error("Failed to persist task ownership metadata: %s", meta_exc)
                    raise ServiceUnavailableException(
                        "Failed to persist task ownership metadata. Task not dispatched.",
                        error_code="TASK_METADATA_PERSISTENCE_FAILED",
                    ) from meta_exc

        # 3. Resolve Celery Task Signature
        resolved_task: Task = self.celery.tasks[task] if isinstance(task, str) else task

        # 4. Dispatch Task to Celery Broker Off-Thread
        def _dispatch() -> str:
            res: AsyncResult = resolved_task.apply_async(
                args=args,
                kwargs=kw,
                queue=queue,
                countdown=countdown,
                task_id=assigned_task_id,
            )
            return str(res.id)

        try:
            task_id = await asyncio.to_thread(_dispatch)
        except Exception as dispatch_exc:
            # Dispatch failed: Roll back idempotency and metadata so no stuck PENDING records remain
            if redis_client is not None:
                try:
                    await redis_client.delete(meta_key)
                    if idempotency_key:
                        await redis_client.delete(f"{IDEMPOTENCY_PREFIX}{idempotency_key}")
                except Exception:
                    pass
            logger.error(
                "Failed to dispatch Celery task %s to broker: %s", assigned_task_id, dispatch_exc
            )
            raise ServiceUnavailableException(
                f"Task broker unavailable: {dispatch_exc}",
                error_code="TASK_DISPATCH_FAILED",
            ) from dispatch_exc

        return TaskSubmissionResult(
            task_id=task_id,
            status="PENDING",
            queue=target_queue,
            duplicate=False,
        )

    async def get_task_metadata(
        self,
        task_id: str,
        redis_client: AsyncRedis[Any] | None,
    ) -> dict[str, Any] | None:
        """Retrieve task ownership and submission metadata from Redis."""
        if redis_client is None:
            return None
        meta_key = f"{TASK_META_PREFIX}{task_id}"
        try:
            raw = await redis_client.get(meta_key)
            if raw:
                return json.loads(str(raw))  # type: ignore[no-any-return]
        except Exception as exc:
            logger.warning("Error fetching task metadata: %s", exc)
        return None

    async def get_task_status(self, task_id: str) -> TaskStatusResult:
        """Query current execution status of a task from Celery result backend."""

        def _query() -> tuple[str, bool, bool | None, str | None, Any | None]:
            async_result = AsyncResult(task_id, app=self.celery)
            state = async_result.state
            is_ready = async_result.ready()
            is_success: bool | None = None
            err_msg: str | None = None
            res_val: Any | None = None

            if is_ready:
                is_success = async_result.successful()
                if is_success:
                    res_val = async_result.result
                else:
                    raw_err = async_result.result
                    err_msg = str(raw_err) if raw_err is not None else "Task execution failed"
            elif state == "STARTED":
                is_success = None
            elif state == "RETRY":
                is_success = None
                raw_err = async_result.result
                err_msg = str(raw_err) if raw_err is not None else "Task retrying"

            return state, is_ready, is_success, err_msg, res_val

        state, is_ready, is_success, err_msg, res_val = await asyncio.to_thread(_query)

        return TaskStatusResult(
            task_id=task_id,
            status=state,
            ready=is_ready,
            successful=is_success,
            error=err_msg,
            result=res_val,
        )

    async def revoke_task(
        self,
        task_id: str,
        terminate: bool = False,
        signal: str = "SIGTERM",
    ) -> bool:
        """Revoke a queued or in-flight Celery task."""

        def _revoke() -> bool:
            self.celery.control.revoke(task_id, terminate=terminate, signal=signal)
            return True

        return await asyncio.to_thread(_revoke)


# Global singleton instance
task_service = TaskService()
