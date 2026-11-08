"""Unit tests for FastAPI TaskService background task submission and lifecycle management."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_task_service_submit_task() -> None:
    """Verify task submission dispatches asynchronously and returns initial metadata."""
    mock_celery = MagicMock()
    mock_async_result = MagicMock()
    mock_async_result.id = "submitted-task-123"
    mock_task = MagicMock()
    mock_task.apply_async.return_value = mock_async_result

    service = TaskService(app_celery=mock_celery)

    result = await service.submit_task(
        task=mock_task,
        args=("hello",),
        queue="default",
    )

    assert result.task_id == "submitted-task-123"
    assert result.status == "PENDING"
    assert result.queue == "default"
    assert result.duplicate is False
    mock_task.apply_async.assert_called_once_with(
        args=("hello",),
        kwargs={},
        queue="default",
        countdown=None,
    )


@pytest.mark.asyncio
async def test_task_service_duplicate_submission_suppressed() -> None:
    """Verify duplicate submission is detected and returns existing task without redispatching."""
    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_async_redis = AsyncMock()

    # Simulate existing lock acquired in Redis
    mock_async_redis.set.return_value = False
    import json

    existing_payload = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "previously-submitted-456",
        }
    )
    mock_async_redis.get.return_value = existing_payload

    service = TaskService(app_celery=mock_celery)

    result = await service.submit_task(
        task=mock_task,
        idempotency_key="unique-client-key-1",
        redis_client=mock_async_redis,
    )

    assert result.duplicate is True
    assert result.task_id == "previously-submitted-456"
    assert result.status == "PROCESSING"
    # Task apply_async must NOT be called on duplicate
    mock_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_task_service_get_task_status_lifecycle() -> None:
    """Verify get_task_status correctly translates Celery AsyncResult states."""
    mock_celery = MagicMock()
    service = TaskService(app_celery=mock_celery)

    with patch("app.services.task_service.AsyncResult") as mock_ar_cls:
        # Case 1: Pending
        mock_ar = MagicMock()
        mock_ar.state = "PENDING"
        mock_ar.ready.return_value = False
        mock_ar_cls.return_value = mock_ar

        res = await service.get_task_status("task-pending")
        assert res.status == "PENDING"
        assert res.ready is False
        assert res.successful is None
        assert res.result is None

        # Case 2: Success
        mock_ar.state = "SUCCESS"
        mock_ar.ready.return_value = True
        mock_ar.successful.return_value = True
        mock_ar.result = {"answer": 42}

        res = await service.get_task_status("task-success")
        assert res.status == "SUCCESS"
        assert res.ready is True
        assert res.successful is True
        assert res.result == {"answer": 42}

        # Case 3: Failure
        mock_ar.state = "FAILURE"
        mock_ar.ready.return_value = True
        mock_ar.successful.return_value = False
        mock_ar.result = ValueError("Database connection lost")

        res = await service.get_task_status("task-failure")
        assert res.status == "FAILURE"
        assert res.ready is True
        assert res.successful is False
        assert "Database connection lost" in str(res.error)


@pytest.mark.asyncio
async def test_task_service_revoke_task() -> None:
    """Verify revoke_task invokes Celery control revocation."""
    mock_celery = MagicMock()
    service = TaskService(app_celery=mock_celery)

    success = await service.revoke_task("task-to-kill", terminate=True)
    assert success is True
    mock_celery.control.revoke.assert_called_once_with("task-to-kill", terminate=True)
