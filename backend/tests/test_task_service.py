"""Unit tests for FastAPI TaskService background task submission and lifecycle management."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.task_service import TaskService


@pytest.mark.asyncio
async def test_task_service_submit_task() -> None:
    """Verify task submission dispatches asynchronously and returns initial metadata."""
    mock_celery = MagicMock()
    mock_async_result = MagicMock()
    mock_task = MagicMock()

    def _fake_apply_async(*args, **kwargs):
        mock_async_result.id = kwargs.get("task_id", "fallback-id")
        return mock_async_result

    mock_task.apply_async.side_effect = _fake_apply_async

    service = TaskService(app_celery=mock_celery)

    result = await service.submit_task(
        task=mock_task,
        args=("hello",),
        queue="default",
    )

    assert result.status == "PENDING"
    assert result.queue == "default"
    assert result.duplicate is False
    assert result.task_id is not None
    assert mock_task.apply_async.call_count == 1
    call_kwargs = mock_task.apply_async.call_args.kwargs
    assert call_kwargs["task_id"] == result.task_id
    assert call_kwargs["queue"] == "default"
    assert call_kwargs["args"] == ("hello",)


@pytest.mark.asyncio
async def test_task_service_duplicate_submission_suppressed() -> None:
    """Verify duplicate submission is detected and returns existing task without redispatching."""
    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_async_redis = AsyncMock()

    # Simulate existing lock acquired in Redis via Lua eval
    existing_payload = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "previously-submitted-456",
        }
    )
    mock_async_redis.eval.return_value = [0, existing_payload]

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
    mock_celery.control.revoke.assert_called_once_with(
        "task-to-kill", terminate=True, signal="SIGTERM"
    )


@pytest.mark.asyncio
async def test_task_service_multi_tenant_idempotency_scoping() -> None:
    """Verify that different tenants using identical idempotency keys get isolated registrations."""
    from uuid import uuid4

    from app.core.tasks.idempotency import IDEMPOTENCY_PREFIX

    tenant_a = uuid4()
    tenant_b = uuid4()
    client_key = "shared-client-key"

    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "sample_scoped_task"
    mock_async_result = MagicMock()
    mock_async_result.id = "assigned-task-1"
    mock_task.apply_async.return_value = mock_async_result

    mock_redis = AsyncMock()
    mock_redis.eval.return_value = [1, "{}"]  # First registration fresh

    service = TaskService(app_celery=mock_celery)

    res_a = await service.submit_task(
        task=mock_task,
        idempotency_key=client_key,
        tenant_id=tenant_a,
        redis_client=mock_redis,
    )
    assert res_a.duplicate is False
    call_a_key = mock_redis.eval.call_args_list[0][0][2]
    assert f"{IDEMPOTENCY_PREFIX}{tenant_a}" in call_a_key

    # Now simulate tenant B submitting with the same client key
    mock_redis.eval.reset_mock()
    mock_redis.eval.return_value = [1, "{}"]
    res_b = await service.submit_task(
        task=mock_task,
        idempotency_key=client_key,
        tenant_id=tenant_b,
        redis_client=mock_redis,
    )
    assert res_b.duplicate is False
    call_b_key = mock_redis.eval.call_args_list[0][0][2]
    assert f"{IDEMPOTENCY_PREFIX}{tenant_b}" in call_b_key
    assert call_a_key != call_b_key


@pytest.mark.asyncio
async def test_task_service_rejects_cross_tenant_idempotency_access() -> None:
    """Verify that attempting to access another tenant's idempotency record raises AuthorizationException."""
    from uuid import uuid4

    from app.core.errors import AuthorizationException

    tenant_a = uuid4()
    tenant_b = uuid4()

    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "scoped_task"

    mock_redis = AsyncMock()
    # Simulate existing record belongs to tenant_a
    existing_data = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "tenant-a-task",
            "tenant_id": str(tenant_a),
        }
    )
    mock_redis.eval.return_value = [0, existing_data]

    service = TaskService(app_celery=mock_celery)

    with pytest.raises(AuthorizationException) as exc_info:
        await service.submit_task(
            task=mock_task,
            idempotency_key="key-collide",
            tenant_id=tenant_b,  # Tenant B requesting
            redis_client=mock_redis,
        )

    assert "Not authorized to access tasks from another organization" in str(exc_info.value)


@pytest.mark.asyncio
async def test_task_service_dispatch_failure_records_dispatch_unknown() -> None:
    """Verify that broker dispatch failure records DISPATCH_UNKNOWN rather than deleting records."""
    from app.core.errors import ServiceUnavailableException

    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "failing_dispatch_task"
    mock_task.apply_async.side_effect = RuntimeError("Broker connection timeout")

    mock_redis = AsyncMock()
    mock_redis.eval.return_value = [1, "{}"]  # Registration succeeds

    service = TaskService(app_celery=mock_celery)

    with pytest.raises(ServiceUnavailableException) as exc_info:
        await service.submit_task(
            task=mock_task,
            idempotency_key="uncertain-key",
            redis_client=mock_redis,
        )

    assert "Task broker unavailable" in str(exc_info.value)
    # Verify that eval was called a second time for LUA_RECORD_DISPATCH_UNKNOWN
    assert mock_redis.eval.call_count == 2
    second_call = mock_redis.eval.call_args_list[1]
    assert "DISPATCH_UNKNOWN" in str(second_call) or "LUA_RECORD_DISPATCH_UNKNOWN" in str(
        second_call
    )
    # Crucially verify delete was NOT called on the idempotency key!
    for delete_call in mock_redis.delete.call_args_list:
        assert "uncertain-key" not in str(delete_call)


@pytest.mark.asyncio
async def test_task_service_reconciles_dispatch_unknown_on_retry() -> None:
    """Verify that retrying a DISPATCH_UNKNOWN task reconciles safely without duplicate execution."""
    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "retry_task"
    mock_async_result = MagicMock()
    mock_async_result.id = "original-task-id-123"
    mock_task.apply_async.return_value = mock_async_result

    mock_redis = AsyncMock()
    # Registration returns existing DISPATCH_UNKNOWN record
    existing_unknown = json.dumps(
        {
            "status": "DISPATCH_UNKNOWN",
            "task_id": "original-task-id-123",
            "tenant_id": None,
        }
    )
    mock_redis.eval.side_effect = [
        [0, existing_unknown],  # register_submission_async returns existing
        1,  # reconcile_dispatch_async succeeds
    ]

    service = TaskService(app_celery=mock_celery)

    # Simulate Celery status check returns PENDING (safe to redispatch with same task ID)
    with patch("app.services.task_service.AsyncResult") as mock_ar_cls:
        mock_ar = MagicMock()
        mock_ar.state = "PENDING"
        mock_ar_cls.return_value = mock_ar

        res = await service.submit_task(
            task=mock_task,
            idempotency_key="key-retry-unknown",
            redis_client=mock_redis,
        )

        assert res.duplicate is True
        assert res.task_id == "original-task-id-123"
        assert res.status == "PENDING"
        # apply_async must have been called with the EXACT same task_id
        mock_task.apply_async.assert_called_once()
        assert mock_task.apply_async.call_args.kwargs["task_id"] == "original-task-id-123"
