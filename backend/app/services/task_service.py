"""Reusable service for asynchronous background task dispatching, status querying, and result retrieval."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from celery import Task
from celery.result import AsyncResult
from pydantic import BaseModel, Field
from redis.asyncio import Redis as AsyncRedis

from app.core.celery_app import celery_app
from app.core.tasks.idempotency import IdempotencyManager

logger = logging.getLogger("app.services.task_service")


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
        redis_client: AsyncRedis[Any] | None = None,
    ) -> TaskSubmissionResult:
        """Submit a background task for asynchronous execution with optional idempotency protection."""
        kw = dict(kwargs) if kwargs else {}
        target_queue = queue or "default"

        # Check idempotency duplicate submission if key is provided and async redis client is available
        if idempotency_key:
            kw["idempotency_key"] = idempotency_key
            if redis_client is not None:
                acquired, existing = await IdempotencyManager.acquire_async(
                    client=redis_client,
                    key=idempotency_key,
                    task_id="pending_submission",
                    lock_ttl=300,
                )
                if not acquired and existing:
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

        # Resolve task function or signature
        resolved_task: Task = self.celery.tasks[task] if isinstance(task, str) else task

        # Dispatch via asyncio.to_thread to prevent blocking the event loop on Redis I/O
        def _dispatch() -> str:
            res: AsyncResult = resolved_task.apply_async(
                args=args,
                kwargs=kw,
                queue=queue,
                countdown=countdown,
            )
            return str(res.id)

        task_id = await asyncio.to_thread(_dispatch)

        # If idempotency key was registered as pending, update with real task ID
        if idempotency_key and redis_client is not None:
            await IdempotencyManager.acquire_async(
                client=redis_client,
                key=idempotency_key,
                task_id=task_id,
                lock_ttl=300,
            )

        return TaskSubmissionResult(
            task_id=task_id,
            status="PENDING",
            queue=target_queue,
            duplicate=False,
        )

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

    async def revoke_task(self, task_id: str, terminate: bool = False) -> bool:
        """Revoke a pending or running Celery task."""

        def _revoke() -> bool:
            try:
                self.celery.control.revoke(task_id, terminate=terminate)
                return True
            except Exception as exc:
                logger.warning("Failed to revoke task %s: %s", task_id, exc)
                return False

        return await asyncio.to_thread(_revoke)


task_service = TaskService()
