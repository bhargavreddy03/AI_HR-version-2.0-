"""Unit and integration tests for FastAPI background task endpoints under /api/v1/tasks."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_application
from app.services.task_service import TaskStatusResult, TaskSubmissionResult


@pytest.fixture
def app_instance():
    """Create a configured test application instance."""
    return create_application()


@pytest.mark.asyncio
async def test_submit_system_ping_endpoint(app_instance) -> None:
    """Verify POST /api/v1/tasks/system/ping dispatches task and returns 202 Accepted."""
    mock_sub_res = TaskSubmissionResult(
        task_id="ping-task-uuid-1",
        status="PENDING",
        queue="default",
        duplicate=False,
    )

    with patch(
        "app.api.v1.tasks.task_service.submit_task",
        new=AsyncMock(return_value=mock_sub_res),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/tasks/system/ping",
                json={"message": "smoke-test"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "ping-task-uuid-1"
        assert data["status"] == "PENDING"
        assert data["queue"] == "default"
        assert data["duplicate"] is False


@pytest.mark.asyncio
async def test_submit_system_ping_duplicate_idempotency(app_instance) -> None:
    """Verify duplicate submission returns duplicate: true flag with existing task ID."""
    mock_dup_res = TaskSubmissionResult(
        task_id="original-ping-task-uuid",
        status="PROCESSING",
        queue="default",
        duplicate=True,
    )

    with patch(
        "app.api.v1.tasks.task_service.submit_task",
        new=AsyncMock(return_value=mock_dup_res),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.post(
                "/api/v1/tasks/system/ping",
                json={"message": "smoke-test"},
                headers={"Idempotency-Key": "client-idempotency-key-123"},
            )

        assert response.status_code == 202
        data = response.json()
        assert data["task_id"] == "original-ping-task-uuid"
        assert data["duplicate"] is True


@pytest.mark.asyncio
async def test_get_task_status_endpoint(app_instance) -> None:
    """Verify GET /api/v1/tasks/{task_id}/status returns task state and metadata."""
    mock_status = TaskStatusResult(
        task_id="test-task-abc",
        status="SUCCESS",
        ready=True,
        successful=True,
        error=None,
        result={"status": "pong"},
    )

    with patch(
        "app.api.v1.tasks.task_service.get_task_status",
        new=AsyncMock(return_value=mock_status),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/tasks/test-task-abc/status")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-abc"
        assert data["status"] == "SUCCESS"
        assert data["ready"] is True
        assert data["successful"] is True
        assert data["error"] is None


@pytest.mark.asyncio
async def test_get_task_result_endpoint(app_instance) -> None:
    """Verify GET /api/v1/tasks/{task_id}/result returns result data on success."""
    mock_status = TaskStatusResult(
        task_id="test-task-xyz",
        status="SUCCESS",
        ready=True,
        successful=True,
        error=None,
        result={"status": "pong", "message": "ping"},
    )

    with patch(
        "app.api.v1.tasks.task_service.get_task_status",
        new=AsyncMock(return_value=mock_status),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/v1/tasks/test-task-xyz/result")

        assert response.status_code == 200
        data = response.json()
        assert data["task_id"] == "test-task-xyz"
        assert data["ready"] is True
        assert data["result"] == {"status": "pong", "message": "ping"}
        assert data["error"] is None
