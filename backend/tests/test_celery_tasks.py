"""Unit tests for Celery task reliability, execution lifecycle, retries, and idempotency."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.core.tasks.base import (
    BaseTask,
    PermanentTaskError,
    TransientTaskError,
)
from app.core.tasks.idempotency import IdempotencyManager, LockHeartbeat, idempotent_task
from app.core.tasks.system import (
    sample_permanent_failure,
    sample_transient_retry,
    system_ping,
)
from app.modules.documents.tasks import parse_document


def test_base_task_payload_sanitization() -> None:
    """Verify BaseTask.sanitize_payload redacts credentials and sensitive attributes."""
    raw_payload = {
        "user_id": "u-123",
        "email": "user@example.com",
        "password": "SuperSecretPassword123!",
        "token": "jwt.token.string",
        "api_key": "sk-1234567890",
        "metadata": {
            "auth_token": "bearer-token",
            "nested_secret": "my-mfa-secret",
            "safe_counter": 42,
        },
        "safe_list": ["item1", {"pepper": "pepper_value", "data": "visible"}],
    }

    sanitized = BaseTask.sanitize_payload(raw_payload)

    assert sanitized["password"] == "******"
    assert sanitized["token"] == "******"
    assert sanitized["api_key"] == "******"
    assert sanitized["metadata"]["auth_token"] == "******"
    assert sanitized["metadata"]["nested_secret"] == "******"
    assert sanitized["metadata"]["safe_counter"] == 42
    assert sanitized["safe_list"][1]["pepper"] == "******"
    assert sanitized["safe_list"][1]["data"] == "visible"
    assert sanitized["user_id"] == "u-123"


def test_system_ping_execution() -> None:
    """Verify system_ping task executes synchronously and returns diagnostic payload."""
    res = system_ping.apply(args=("test-ping",))
    assert res.successful() is True
    data = res.result
    assert data["status"] == "pong"
    assert data["message"] == "test-ping"
    assert "timestamp" in data
    assert "queue" in data


def test_system_ping_execution_with_idempotency_key() -> None:
    """Verify system_ping task accepts and respects idempotency_key."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = [
        [1, "ping-token-1", "{}"],  # acquire
        1,  # complete
    ]
    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = system_ping.apply(args=("test-ping",), kwargs={"idempotency_key": "ping-key-1"})
        assert res.successful() is True
        data = res.result
        assert data["status"] == "pong"
        assert data["idempotency_key"] == "ping-key-1"


def test_sample_transient_retry_eventual_success() -> None:
    """Verify transient task failure raises TransientTaskError and succeeds once threshold reached."""
    sample_transient_retry.push_request(
        retries=0, id="mock-task-1", delivery_info={"routing_key": "default"}
    )
    try:
        with pytest.raises(TransientTaskError) as exc_info:
            sample_transient_retry.run(fail_until_attempt=2, payload="retry-test")
        assert "Transient network blip on attempt 1" in str(exc_info.value)
    finally:
        sample_transient_retry.pop_request()

    sample_transient_retry.push_request(
        retries=1, id="mock-task-1", delivery_info={"routing_key": "default"}
    )
    try:
        result = sample_transient_retry.run(fail_until_attempt=2, payload="retry-test")
        assert result["status"] == "success"
        assert result["attempts_required"] == 2
        assert result["payload"] == "retry-test"
    finally:
        sample_transient_retry.pop_request()


def test_sample_permanent_failure_no_retry() -> None:
    """Verify permanent failure raises PermanentTaskError immediately without scheduling retries."""
    sample_permanent_failure.push_request(retries=0, id="mock-task-perm")
    try:
        with pytest.raises(PermanentTaskError) as exc_info:
            sample_permanent_failure.run(error_message="Invalid candidate document schema")
        assert "Permanent business validation error" in str(exc_info.value)
    finally:
        sample_permanent_failure.pop_request()


def test_parse_document_task_execution() -> None:
    """Verify document processing sample task routes to document_processing and executes."""
    res = parse_document.apply(
        kwargs={
            "document_id": "doc-456",
            "tenant_id": "org-789",
            "s3_key": "resumes/doc-456.pdf",
        }
    )
    assert res.successful() is True
    data = res.result
    assert data["status"] == "completed"
    assert data["document_id"] == "doc-456"
    assert data["tenant_id"] == "org-789"


def test_idempotent_task_decorator_caches_result() -> None:
    """Verify @idempotent_task returns cached execution result on second execution."""
    mock_redis = MagicMock()
    # 1st call: eval acquire returns [1, token, payload], eval complete returns 1
    # 2nd call: eval acquire returns [0, None, cached_payload]
    cached_payload = json.dumps(
        {
            "status": "COMPLETED",
            "task_id": "original-task-id",
            "result": {"status": "processed", "value": 10, "computed": 20},
        }
    )
    mock_redis.eval.side_effect = [
        [1, "mock-token-1", "{}"],  # acquire
        1,  # complete
        [0, None, cached_payload],  # 2nd acquire
    ]

    execution_counter = 0

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(val: int, idempotency_key: str | None = None) -> dict[str, int]:
        nonlocal execution_counter
        execution_counter += 1
        return {"val": val}

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res1 = sample_fn(10, idempotency_key="key-abc")
        assert res1 == {"val": 10}
        assert execution_counter == 1

        res2 = sample_fn(10, idempotency_key="key-abc")
        assert res2 == {"status": "processed", "value": 10, "computed": 20}
        assert execution_counter == 1


def test_idempotent_task_suppresses_concurrent_execution() -> None:
    """Verify duplicate running execution is suppressed when lock is already in PROCESSING state."""
    mock_redis = MagicMock()
    processing_payload = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "concurrent-worker-1",
        }
    )
    mock_redis.eval.return_value = [0, None, processing_payload]

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(val: int, idempotency_key: str | None = None) -> dict[str, int]:
        return {"val": val}

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_fn(5, idempotency_key="running-key")
        assert res["status"] == "duplicate_execution_suppressed"
        assert res["original_task_id"] == "concurrent-worker-1"


def test_idempotent_task_releases_lock_on_transient_error() -> None:
    """Verify lock is released with lock_token when TransientTaskError is raised so retries can proceed."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = [
        [1, "token-for-release", "{}"],  # acquire
        1,  # release
    ]

    @idempotent_task(key_param="idempotency_key")
    def failing_fn(idempotency_key: str | None = None) -> None:
        raise TransientTaskError("Temporary failure")

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        with pytest.raises(TransientTaskError):
            failing_fn(idempotency_key="retry-key")

        assert mock_redis.eval.call_count == 2
        # Verify second eval called release with token
        call_args = mock_redis.eval.call_args_list[1]
        assert "LUA_RELEASE" in str(call_args) or "DEL" in str(call_args[0][0])
        assert call_args[0][3] == "token-for-release"


def test_idempotency_manager_lock_token_protection() -> None:
    """Verify IdempotencyManager rejects completion or release if lock token does not match."""
    mock_redis = MagicMock()
    # eval returning 0 indicates lock token mismatch in Redis Lua script
    mock_redis.eval.return_value = 0

    manager = IdempotencyManager(sync_client=mock_redis)

    # Wrong token cannot complete
    completed = manager.complete("key-1", result="data", task_id="t-1", lock_token="wrong-token")
    assert completed is False

    # Wrong token cannot release
    released = manager.release("key-1", lock_token="wrong-token")
    assert released is False


def test_format_scoped_key_multi_tenant_isolation() -> None:
    """Verify that format_scoped_key properly scopes keys across tenants, users, and tasks."""
    from uuid import uuid4

    from app.core.tasks.idempotency import format_scoped_key

    tenant_a = uuid4()
    tenant_b = uuid4()
    user_1 = uuid4()
    user_2 = uuid4()
    client_key = "report-generation-123"

    key_ta_u1 = format_scoped_key(
        client_key, tenant_id=tenant_a, user_id=user_1, task_type="generate_report"
    )
    key_tb_u1 = format_scoped_key(
        client_key, tenant_id=tenant_b, user_id=user_1, task_type="generate_report"
    )
    key_ta_u2 = format_scoped_key(
        client_key, tenant_id=tenant_a, user_id=user_2, task_type="generate_report"
    )
    key_ta_diff_task = format_scoped_key(
        client_key, tenant_id=tenant_a, user_id=user_1, task_type="export_csv"
    )

    # All scoped keys must be distinct to prevent cross-tenant and cross-user collision
    assert key_ta_u1 != key_tb_u1
    assert key_ta_u1 != key_ta_u2
    assert key_ta_u1 != key_ta_diff_task
    assert str(tenant_a) in key_ta_u1
    assert str(tenant_b) in key_tb_u1
    assert client_key in key_ta_u1


def test_idempotency_manager_lock_renewal() -> None:
    """Verify lock renewal succeeds only when matching lock_token is supplied."""
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = [1, 0]  # First renewal succeeds, second fails (wrong token)

    manager = IdempotencyManager(sync_client=mock_redis)

    # Valid token renews lock
    assert manager.renew("key-renew", lock_token="valid-token", extend_ttl=360) is True

    # Empty/missing token is rejected without calling Redis
    assert manager.renew("key-renew", lock_token="") is False
    assert manager.renew("key-renew", lock_token=None) is False

    # Mismatched token rejected by Lua
    assert manager.renew("key-renew", lock_token="expired-or-stolen-token") is False


def test_idempotent_task_bounded_lease_exceeds_task_time_limit() -> None:
    """Verify idempotent_task bounds lock TTL to at least CELERY_TASK_TIME_LIMIT + 60."""
    from app.core.config import get_settings

    settings = get_settings()
    mock_redis = MagicMock()
    mock_redis.eval.side_effect = [
        [1, "bounded-token", "{}"],  # acquire
        1,  # complete
    ]

    @idempotent_task(key_param="idempotency_key", lock_ttl=10)  # Caller requested small 10s TTL
    def sample_bounded(val: int, idempotency_key: str | None = None) -> int:
        return val * 2

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        sample_bounded(5, idempotency_key="bounded-test-key")

        # First call is acquire: verify the lock_ttl passed to Lua is at least CELERY_TASK_TIME_LIMIT + 60
        call_args = mock_redis.eval.call_args_list[0]
        actual_lock_ttl = int(call_args[0][5])  # ARGV[3] is lock_ttl
        expected_min = settings.CELERY_TASK_TIME_LIMIT + 60
        assert actual_lock_ttl >= expected_min


def test_format_scoped_key_prevents_prefix_injection_and_bypass() -> None:
    """Verify malicious client cannot bypass tenant isolation by prefixing idempotency key with idempotency:task:."""
    from uuid import uuid4

    from app.core.tasks.idempotency import IDEMPOTENCY_PREFIX, format_scoped_key

    tenant_attacker = uuid4()
    tenant_victim = uuid4()

    # Malicious client sends a key crafted to impersonate victim tenant
    crafted_key = f"{IDEMPOTENCY_PREFIX}{tenant_victim}:admin:system_ping:victim-payment-1"

    scoped_key = format_scoped_key(
        key=crafted_key,
        tenant_id=tenant_attacker,
        user_id="attacker-user",
        task_type="system_ping",
    )

    # Scoped key must strictly reside within tenant_attacker's namespace
    expected_prefix = f"{IDEMPOTENCY_PREFIX}{tenant_attacker}:attacker-user:system_ping:"
    assert scoped_key.startswith(expected_prefix)
    assert str(tenant_attacker) in scoped_key

    # It must never match the victim's legitimate scoped key
    victim_key = format_scoped_key(
        key="victim-payment-1",
        tenant_id=tenant_victim,
        user_id="admin",
        task_type="system_ping",
    )
    assert scoped_key != victim_key


def test_delayed_worker_execution_acquires_long_waiting_pending_task() -> None:
    """Verify that a worker picking up a task delayed in queue (e.g. > 360s) transitions PENDING to PROCESSING."""
    mock_redis = MagicMock()
    # Lua acquire transitions PENDING to PROCESSING with worker lock lease
    mock_redis.eval.side_effect = [
        [1, "worker-token-xyz", "{}"],  # acquire succeeds
        1,  # complete succeeds
    ]

    manager = IdempotencyManager(sync_client=mock_redis)

    # Worker acquires lock for the delayed task
    acquired, token, existing = manager.acquire(
        key="delayed-scoped-key",
        task_id="original-delayed-task-id",
        lock_ttl=360,
    )
    assert acquired is True
    assert token == "worker-token-xyz"

    # Worker completes the delayed task
    completed = manager.complete(
        key="delayed-scoped-key",
        result={"status": "finished"},
        task_id="original-delayed-task-id",
        lock_token=token,
        result_ttl=86400,
    )
    assert completed is True


def test_idempotent_task_fails_closed_when_acquisition_fails() -> None:
    """FINDING 1: Verify underlying task function NEVER executes if lock acquisition fails."""
    mock_redis = MagicMock()
    # Simulate acquire returning failure with an unhandled/corrupted state
    mock_redis.eval.return_value = [0, None, json.dumps({"status": "CORRUPTED_OR_UNKNOWN"})]

    call_count = 0

    @idempotent_task(key_param="idempotency_key")
    def sensitive_task(val: int, idempotency_key: str | None = None) -> int:
        nonlocal call_count
        call_count += 1
        return val * 10

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        with pytest.raises(PermanentTaskError) as exc_info:
            sensitive_task(5, idempotency_key="fail-closed-key")

        assert "Unprotected task execution prevented" in str(exc_info.value)
        # Crucial check: Underlying task was NEVER called!
        assert call_count == 0


def test_idempotent_task_fails_closed_on_failed_state() -> None:
    """FINDING 1: Verify that a task previously in FAILED state never re-executes automatically."""
    mock_redis = MagicMock()
    failed_payload = json.dumps(
        {
            "status": "FAILED",
            "task_id": "failed-task-123",
            "error": "Database constraint violation",
        }
    )
    mock_redis.eval.return_value = [0, None, failed_payload]

    execution_count = 0

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(idempotency_key: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "should-never-run"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_fn(idempotency_key="key-failed-task")
        assert res["status"] == "task_previously_failed"
        assert res["original_task_id"] == "failed-task-123"
        assert res["error"] == "Database constraint violation"
        assert execution_count == 0


def test_idempotent_task_safe_recovery_transition_from_dispatch_unknown() -> None:
    """FINDING 1: Verify DISPATCH_UNKNOWN with matching task_id safely recovers and executes."""
    mock_redis = MagicMock()
    unknown_payload = json.dumps(
        {
            "status": "DISPATCH_UNKNOWN",
            "task_id": "matching-worker-task-1",
        }
    )
    # 1. Acquire transitions DISPATCH_UNKNOWN to PROCESSING for matching task_id
    mock_redis.eval.side_effect = [
        [1, "recovered-token-1", unknown_payload],  # acquire
        1,  # complete
    ]

    execution_count = 0

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(idempotency_key: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "recovered-success"

    # Simulate Celery task instance with matching request.id
    class FakeTask:
        def __init__(self) -> None:
            self.request = MagicMock(id="matching-worker-task-1", headers={})
            self.name = "fake_task"

    fake_task = FakeTask()

    @idempotent_task(key_param="idempotency_key")
    def sample_bound_fn(self: Any, idempotency_key: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "recovered-success"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_bound_fn(fake_task, idempotency_key="recovery-key")
        assert res == "recovered-success"
        assert execution_count == 1


def test_heartbeat_distinguishes_transient_network_error_from_confirmed_loss() -> None:
    """FINDING 4: Verify heartbeat retries transient network errors without falsely marking ownership lost."""
    import redis

    mock_redis = MagicMock()
    # 1st call throws connection error, 2nd succeeds with renewed
    mock_redis.eval.side_effect = [
        redis.ConnectionError("Temporary Redis connection timeout"),
        [1, "RENEWED"],
    ]

    manager = IdempotencyManager(sync_client=mock_redis)
    heartbeat = LockHeartbeat(
        manager=manager,
        key="test-key",
        lock_token="valid-token",
        interval=0.05,
        extend_ttl=360,
        max_consecutive_network_failures=3,
    )
    heartbeat.start()
    import time

    time.sleep(0.15)
    heartbeat.stop()

    # Heartbeat must NOT have marked ownership lost because connection recovered
    assert heartbeat.is_ownership_lost() is False


def test_heartbeat_confirms_ownership_lost_on_expired_or_mismatched_token() -> None:
    """FINDING 4: Verify heartbeat immediately marks ownership lost when Redis confirms token mismatch."""
    mock_redis = MagicMock()
    # Redis confirms TOKEN_MISMATCH (another worker stole lock)
    mock_redis.eval.return_value = [0, "TOKEN_MISMATCH"]

    manager = IdempotencyManager(sync_client=mock_redis)
    heartbeat = LockHeartbeat(
        manager=manager,
        key="test-key",
        lock_token="stale-token",
        interval=0.05,
        extend_ttl=360,
    )
    heartbeat.start()
    import time

    time.sleep(0.12)
    heartbeat.stop()

    assert heartbeat.is_ownership_lost() is True
    assert heartbeat.loss_reason == "TOKEN_MISMATCH"


def test_idempotent_task_aborts_if_lock_ownership_lost_during_execution() -> None:
    """FINDING 4: Verify task raises PermanentTaskError if heartbeat detected lock loss during execution."""
    mock_redis = MagicMock()
    # 1. Acquire succeeds
    # 2. Heartbeat renewal returns TOKEN_MISMATCH
    mock_redis.eval.side_effect = [
        [1, "worker-token-lost", "{}"],  # acquire
        [0, "TOKEN_MISMATCH"],  # heartbeat renewal
    ]

    @idempotent_task(key_param="idempotency_key", lock_ttl=60, heartbeat_interval=0.03)
    def long_task(idempotency_key: str | None = None) -> str:
        import time

        time.sleep(0.12)  # Allow heartbeat to fire and detect TOKEN_MISMATCH
        return "finished-computation"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        with pytest.raises(PermanentTaskError) as exc_info:
            long_task(idempotency_key="ownership-loss-key")

        assert "lock ownership lost during execution" in str(exc_info.value)


def test_worker_with_mismatched_task_id_cannot_acquire_pending_or_dispatch_unknown() -> None:
    """DEFECT 2: Verify worker with mismatched task_id cannot acquire existing PENDING or DISPATCH_UNKNOWN record."""
    mock_redis = MagicMock()
    # Acquire returns failure because task_id does not match registered_task_1
    pending_payload = json.dumps({"status": "PENDING", "task_id": "registered-task-1"})
    mock_redis.eval.return_value = [0, None, pending_payload]

    execution_count = 0

    class MismatchedWorkerTask:
        def __init__(self) -> None:
            self.request = MagicMock(id="intruder-task-2", headers={})
            self.name = "mismatched_task"

    fake_task = MismatchedWorkerTask()

    @idempotent_task(key_param="idempotency_key")
    def sample_task(self: Any, idempotency_key: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "intruder-executed"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_task(fake_task, idempotency_key="mismatch-key")
        # Duplicate execution suppressed; fn must NEVER execute
        assert res["status"] == "duplicate_execution_suppressed"
        assert res["original_task_id"] == "registered-task-1"
        assert execution_count == 0


def test_standalone_task_id_cannot_bypass_task_id_matching() -> None:
    """DEFECT 2: Verify invocation with task_id='standalone' cannot bypass task_id matching for existing submission."""
    mock_redis = MagicMock()
    # When Lua executes, data.task_id == task_id fails because 'registered-task-1' != 'standalone'
    pending_payload = json.dumps({"status": "PENDING", "task_id": "registered-task-1"})
    mock_redis.eval.return_value = [0, None, pending_payload]

    execution_count = 0

    class StandaloneWorkerTask:
        def __init__(self) -> None:
            self.request = MagicMock(id="standalone", headers={})
            self.name = "standalone_task"

    fake_task = StandaloneWorkerTask()

    @idempotent_task(key_param="idempotency_key")
    def sample_task(self: Any, idempotency_key: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "standalone-executed"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_task(fake_task, idempotency_key="standalone-bypass-key")
        assert res["status"] == "duplicate_execution_suppressed"
        assert res["original_task_id"] == "registered-task-1"
        assert execution_count == 0


def test_bound_celery_task_missing_request_id_fails_closed() -> None:
    """DEFECT 2: Verify bound Celery task without a valid request ID fails closed with PermanentTaskError."""

    class MissingIdTask:
        def __init__(self) -> None:
            self.request = MagicMock(id=None, headers={})
            self.name = "missing_id_task"

    fake_task = MissingIdTask()

    @idempotent_task(key_param="idempotency_key")
    def sample_task(self: Any, idempotency_key: str | None = None) -> str:
        return "should-never-run"

    with pytest.raises(PermanentTaskError) as exc_info:
        sample_task(fake_task, idempotency_key="missing-req-id-key")

    assert "Celery request ID is required" in str(exc_info.value)


def test_direct_invocation_ignores_caller_supplied_task_id() -> None:
    """Verify direct function calls always generate random internal ID and never trust caller-supplied task_id."""
    mock_redis = MagicMock()
    # Redis has an existing PENDING record registered with task_id="celery-task-456"
    pending_payload = json.dumps({"status": "PENDING", "task_id": "celery-task-456"})
    mock_redis.eval.return_value = [0, None, pending_payload]

    execution_count = 0

    @idempotent_task(key_param="idempotency_key")
    def sample_direct_fn(idempotency_key: str | None = None, task_id: str | None = None) -> str:
        nonlocal execution_count
        execution_count += 1
        return "direct-hijack-attempt"

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        # Caller directly invokes and tries to supply the registered task_id="celery-task-456"
        res = sample_direct_fn(idempotency_key="resume-123", task_id="celery-task-456")

        # Must NOT execute
        assert execution_count == 0
        assert res["status"] == "duplicate_execution_suppressed"
        assert res["original_task_id"] == "celery-task-456"

        # Verify that mock_redis.eval was called with a generated "direct:..." ID, NOT "celery-task-456"
        eval_args = mock_redis.eval.call_args[0]
        # In LUA_ACQUIRE, ARGV[1] is task_id (index 3 in eval args: script, numkeys, key, task_id, ...)
        passed_task_id = eval_args[3]
        assert passed_task_id.startswith("direct:")
        assert passed_task_id != "celery-task-456"


def test_bound_celery_task_ignores_caller_task_id_when_request_id_missing() -> None:
    """Verify bound Celery tasks only accept self.request.id and reject execution even if kwargs has task_id."""

    class MissingIdTask:
        def __init__(self) -> None:
            self.request = MagicMock(id=None, headers={})
            self.name = "missing_id_with_kwargs_task"

    fake_task = MissingIdTask()

    @idempotent_task(key_param="idempotency_key")
    def sample_task(
        self: Any, idempotency_key: str | None = None, task_id: str | None = None
    ) -> str:
        return "should-never-run"

    # Even if caller passes task_id="celery-task-456" in kwargs, missing self.request.id must fail closed
    with pytest.raises(PermanentTaskError) as exc_info:
        sample_task(fake_task, idempotency_key="key-test", task_id="celery-task-456")

    assert "Celery request ID is required" in str(exc_info.value)
