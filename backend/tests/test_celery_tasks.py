"""Unit tests for Celery task reliability, execution lifecycle, retries, and idempotency."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.tasks.base import (
    BaseTask,
    PermanentTaskError,
    TransientTaskError,
)
from app.core.tasks.idempotency import idempotent_task
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


def test_sample_transient_retry_eventual_success() -> None:
    """Verify transient task failure raises TransientTaskError and succeeds once threshold reached."""
    # First attempt (retries = 0 -> current_attempt = 1 < 2) must raise TransientTaskError
    sample_transient_retry.push_request(
        retries=0, id="mock-task-1", delivery_info={"routing_key": "default"}
    )
    try:
        with pytest.raises(TransientTaskError) as exc_info:
            sample_transient_retry.run(fail_until_attempt=2, payload="retry-test")
        assert "Transient network blip on attempt 1" in str(exc_info.value)
    finally:
        sample_transient_retry.pop_request()

    # Second attempt (retries = 1 -> current_attempt = 2 == 2) succeeds
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
    # First call: set returns True (acquired)
    mock_redis.set.side_effect = [
        True,  # acquire
        True,  # complete
        False,  # second acquire
    ]
    # Second call: get returns cached completed payload
    import json

    cached_payload = json.dumps(
        {
            "status": "COMPLETED",
            "task_id": "original-task-id",
            "result": {"status": "processed", "value": 10, "computed": 20},
        }
    )
    mock_redis.get.return_value = cached_payload

    execution_counter = 0

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(val: int, idempotency_key: str | None = None) -> dict[str, int]:
        nonlocal execution_counter
        execution_counter += 1
        return {"val": val}

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        # 1st call
        res1 = sample_fn(10, idempotency_key="key-abc")
        assert res1 == {"val": 10}
        assert execution_counter == 1

        # 2nd call with same key should return cached result without incrementing counter
        res2 = sample_fn(10, idempotency_key="key-abc")
        assert res2 == {"status": "processed", "value": 10, "computed": 20}
        assert execution_counter == 1


def test_idempotent_task_suppresses_concurrent_execution() -> None:
    """Verify duplicate running execution is suppressed when lock is already in PROCESSING state."""
    mock_redis = MagicMock()
    # acquire returns False because key exists
    mock_redis.set.return_value = False
    import json

    processing_payload = json.dumps(
        {
            "status": "PROCESSING",
            "task_id": "concurrent-worker-1",
        }
    )
    mock_redis.get.return_value = processing_payload

    @idempotent_task(key_param="idempotency_key")
    def sample_fn(val: int, idempotency_key: str | None = None) -> dict[str, int]:
        return {"val": val}

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        res = sample_fn(5, idempotency_key="running-key")
        assert res["status"] == "duplicate_execution_suppressed"
        assert res["original_task_id"] == "concurrent-worker-1"


def test_idempotent_task_releases_lock_on_transient_error() -> None:
    """Verify lock is released when TransientTaskError is raised so retries can proceed."""
    mock_redis = MagicMock()
    mock_redis.set.return_value = True

    @idempotent_task(key_param="idempotency_key")
    def failing_fn(idempotency_key: str | None = None) -> None:
        raise TransientTaskError("Temporary failure")

    with patch("app.core.tasks.idempotency.get_sync_redis_client", return_value=mock_redis):
        with pytest.raises(TransientTaskError):
            failing_fn(idempotency_key="retry-key")

        # Must have called delete to release lock
        mock_redis.delete.assert_called_once_with("idempotency:task:retry-key")
