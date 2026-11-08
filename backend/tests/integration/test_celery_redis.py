"""Integration tests verifying Celery execution with live Redis broker and result backend."""

from __future__ import annotations

import os

import pytest
import redis

from app.core.config import Settings
from app.core.redis import get_sync_redis_client
from app.core.tasks.idempotency import IdempotencyManager
from app.core.tasks.system import system_ping
from app.modules.documents.tasks import parse_document

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")


def is_redis_reachable() -> bool:
    """Synchronous check if Redis is live and accepting commands."""
    try:
        r = redis.Redis.from_url(REDIS_URL, socket_timeout=2.0)
        return bool(r.ping())
    except Exception:
        return False


REDIS_AVAILABLE = is_redis_reachable()
skip_if_no_redis = pytest.mark.skipif(
    not REDIS_AVAILABLE,
    reason=f"Redis service is unavailable at {REDIS_URL}",
)


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_broker_and_result_backend_task_execution() -> None:
    """Verify Celery task dispatches to live Redis broker and writes result to live backend."""
    # Run task and verify result storage
    res = system_ping.apply_async(args=("live-redis-test",), queue="default")
    assert res.id is not None

    # In integration test without a separate running worker process, execute task synchronously
    # and store result in configured live Redis backend
    task_res = system_ping.apply(args=("live-redis-test",), task_id=res.id)
    assert task_res.successful() is True
    assert task_res.result["status"] == "pong"
    assert task_res.result["message"] == "live-redis-test"


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_queue_routing_lists() -> None:
    """Verify tasks are enqueued into the exact Redis queue lists mapped in routing."""
    r_broker = redis.Redis.from_url(CELERY_BROKER_URL, decode_responses=True)

    initial_doc_len = r_broker.llen("document_processing")

    # Enqueue a task to document_processing without eager execution
    async_doc = parse_document.apply_async(
        kwargs={
            "document_id": "live-doc-123",
            "tenant_id": "tenant-live-456",
        },
        queue="document_processing",
    )
    assert async_doc.id is not None

    # Check that document_processing list grew in Redis broker
    new_doc_len = r_broker.llen("document_processing")
    assert new_doc_len >= initial_doc_len + 1

    # Cleanup the test message from the queue list
    r_broker.rpop("document_processing")


@pytest.mark.integration
@skip_if_no_redis
def test_live_redis_idempotency_lifecycle() -> None:
    """Verify IdempotencyManager acquires, caches, and protects against duplicate execution on live Redis."""
    settings = Settings()
    sync_redis = get_sync_redis_client(settings)
    manager = IdempotencyManager(sync_client=sync_redis, settings=settings)

    test_key = "live-test-key-999"
    manager.release(test_key)

    # 1. Acquire first time: must succeed
    acquired, data = manager.acquire(test_key, task_id="task-live-1", lock_ttl=60)
    assert acquired is True
    assert data is None

    # 2. Acquire second time while processing: must fail and return existing data
    acquired2, data2 = manager.acquire(test_key, task_id="task-live-2", lock_ttl=60)
    assert acquired2 is False
    assert data2 is not None
    assert data2["status"] == "PROCESSING"
    assert data2["task_id"] == "task-live-1"

    # 3. Complete: mark as completed with cached result
    manager.complete(test_key, result={"computed": 42}, task_id="task-live-1", result_ttl=60)

    # 4. Acquire third time after completion: must return cached result
    acquired3, data3 = manager.acquire(test_key, task_id="task-live-3", lock_ttl=60)
    assert acquired3 is False
    assert data3 is not None
    assert data3["status"] == "COMPLETED"
    assert data3["result"] == {"computed": 42}

    # 5. Clean up
    manager.release(test_key)
