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


@pytest.mark.asyncio
async def test_task_service_delayed_queue_execution_and_duplicate_submission() -> None:
    """Verify that a task waiting in a queue longer than 360s retains its PENDING idempotency record.

    A duplicate submission after the original 360-second period must be recognized
    as duplicate and suppressed, without dispatching a duplicate task.
    """
    from uuid import uuid4

    from app.core.tasks.idempotency import DEFAULT_SUBMISSION_TTL

    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "delayed_sample_task"
    mock_async_result = MagicMock()
    mock_async_result.id = "original-delayed-task-id"
    mock_task.apply_async.return_value = mock_async_result

    tenant_id = uuid4()
    client_key = "delayed-task-client-key"

    mock_redis = AsyncMock()

    # Step 1: Initial submission at t=0
    mock_redis.eval.return_value = [1, "{}"]  # Fresh registration
    service = TaskService(app_celery=mock_celery)

    res1 = await service.submit_task(
        task=mock_task,
        idempotency_key=client_key,
        tenant_id=tenant_id,
        redis_client=mock_redis,
    )
    assert res1.duplicate is False
    assert res1.status == "PENDING"
    assert res1.task_id is not None
    orig_task_id = res1.task_id

    # Verify that registration used DEFAULT_SUBMISSION_TTL (86400s), NOT the worker lock lease 360s
    reg_eval_call = mock_redis.eval.call_args_list[0]
    actual_ttl = int(reg_eval_call[0][4])  # ARGV[2] is submission_ttl
    assert actual_ttl == DEFAULT_SUBMISSION_TTL
    assert actual_ttl >= 86400

    # Step 2: Simulate delayed execution - e.g. 600 seconds (10 minutes) later, the task is still in Celery queue
    # The client retries or sends a duplicate request with the same Idempotency-Key
    mock_redis.eval.reset_mock()
    mock_task.apply_async.reset_mock()

    pending_record = json.dumps(
        {
            "status": "PENDING",
            "task_id": orig_task_id,
            "tenant_id": str(tenant_id),
            "created_at": "2026-11-08T19:00:00+00:00",
        }
    )
    # Redis still holds the record (has not expired after 360s)
    mock_redis.eval.return_value = [0, pending_record]

    res2 = await service.submit_task(
        task=mock_task,
        idempotency_key=client_key,
        tenant_id=tenant_id,
        redis_client=mock_redis,
    )

    # Must be recognized as duplicate and suppressed
    assert res2.duplicate is True
    assert res2.task_id == orig_task_id
    assert res2.status == "PENDING"
    # apply_async must NOT be called on duplicate
    mock_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_task_service_crafted_prefix_key_cannot_collide_across_tenants() -> None:
    """Verify that an attacker attempting to use an idempotency:task: crafted key cannot access victim data."""
    from uuid import uuid4

    from app.core.tasks.idempotency import IDEMPOTENCY_PREFIX

    tenant_victim = uuid4()
    tenant_attacker = uuid4()

    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "critical_task"
    mock_task.apply_async.return_value = MagicMock(id="attacker-task-id")

    mock_redis = AsyncMock()
    mock_redis.eval.return_value = [1, "{}"]

    service = TaskService(app_celery=mock_celery)

    # Attacker passes a crafted key attempting to target tenant_victim
    crafted_key = f"{IDEMPOTENCY_PREFIX}{tenant_victim}:user1:critical_task:victim-operation"

    await service.submit_task(
        task=mock_task,
        idempotency_key=crafted_key,
        tenant_id=tenant_attacker,
        redis_client=mock_redis,
    )

    # Check the key actually passed to Redis
    actual_redis_key = mock_redis.eval.call_args[0][2]
    # It must be scoped under tenant_attacker, preventing any collision with tenant_victim
    assert f"{IDEMPOTENCY_PREFIX}{tenant_attacker}" in actual_redis_key
    assert actual_redis_key.startswith(f"{IDEMPOTENCY_PREFIX}{tenant_attacker}")


@pytest.mark.asyncio
async def test_reconciliation_skips_redispatch_if_worker_already_acquired() -> None:
    """FINDING 2: Verify API reconciliation racing with worker acquisition never overwrites PROCESSING."""
    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "racing_task"

    mock_redis = AsyncMock()
    existing_unknown = json.dumps(
        {
            "status": "DISPATCH_UNKNOWN",
            "task_id": "racing-task-id",
            "tenant_id": None,
        }
    )
    processing_payload = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "racing-task-id",
            "lock_token": "active-worker-token",
        }
    )
    # 1. register returns existing DISPATCH_UNKNOWN
    # 2. reconcile_dispatch_async returns rejection because worker acquired concurrently
    mock_redis.eval.side_effect = [
        [0, existing_unknown],  # register
        [0, "IMMUTABLE_STATE_PROCESSING", processing_payload],  # reconcile
    ]

    service = TaskService(app_celery=mock_celery)

    with patch("app.services.task_service.AsyncResult") as mock_ar_cls:
        mock_ar = MagicMock()
        mock_ar.state = "PENDING"
        mock_ar_cls.return_value = mock_ar

        res = await service.submit_task(
            task=mock_task,
            idempotency_key="racing-key",
            redis_client=mock_redis,
        )

        assert res.duplicate is True
        assert res.task_id == "racing-task-id"
        assert res.status == "PROCESSING"
        # Must NOT re-dispatch when worker has already acquired
        mock_task.apply_async.assert_not_called()


@pytest.mark.asyncio
async def test_record_dispatch_unknown_preserves_completed_task() -> None:
    """FINDING 3: Verify publish error never overwrites a task already completed by a fast worker."""
    mock_celery = MagicMock()
    mock_task = MagicMock()
    mock_task.name = "fast_worker_task"
    mock_task.apply_async.side_effect = RuntimeError("Socket read timeout from broker")

    mock_redis = AsyncMock()
    completed_payload = json.dumps(
        {
            "status": "COMPLETED",
            "task_id": "fast-task-id",
            "result": {"computed": 100},
        }
    )
    # 1. Registration succeeds
    # 2. record_dispatch_unknown returns rejection because worker already COMPLETED the task
    mock_redis.eval.side_effect = [
        [1, "{}"],  # register
        [0, "IMMUTABLE_STATE_COMPLETED", completed_payload],  # record_dispatch_unknown
    ]

    service = TaskService(app_celery=mock_celery)

    res = await service.submit_task(
        task=mock_task,
        idempotency_key="fast-worker-key",
        redis_client=mock_redis,
    )

    # Must recognise that task completed successfully and preserve result
    assert res.duplicate is True
    assert res.status == "COMPLETED"
    assert res.task_id is not None
