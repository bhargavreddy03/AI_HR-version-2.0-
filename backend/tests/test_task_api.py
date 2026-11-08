"""Unit and integration tests for FastAPI background task endpoints under /api/v1/tasks.

Verifies strict authentication enforcement, tenant isolation boundary, and task query authorization.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import SecurityContext
from app.main import create_application
from app.modules.auth.dependencies import require_authenticated_user
from app.services.task_service import TaskStatusResult, TaskSubmissionResult

TENANT_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = uuid.UUID("22222222-2222-2222-2222-222222222222")
USER_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
USER_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@pytest.fixture
def app_instance():
    """Create a configured test application instance."""
    return create_application()


@pytest.fixture
def auth_context_tenant_a():
    """SecurityContext for a standard authenticated member of Tenant A."""
    return SecurityContext(
        user_id=USER_A,
        session_id=uuid.uuid4(),
        tenant_id=TENANT_A,
        roles=["recruiter"],
        permissions=["recruiter:read", "recruiter:write"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )


@pytest.fixture
def auth_context_tenant_b():
    """SecurityContext for a standard authenticated member of Tenant B."""
    return SecurityContext(
        user_id=USER_B,
        session_id=uuid.uuid4(),
        tenant_id=TENANT_B,
        roles=["recruiter"],
        permissions=["recruiter:read", "recruiter:write"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected(app_instance) -> None:
    """Verify background task endpoints reject unauthenticated requests with 401."""
    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res_post = await ac.post("/api/v1/tasks/system/ping", json={"message": "ping"})
        assert res_post.status_code == 401

        res_status = await ac.get("/api/v1/tasks/test-task-123/status")
        assert res_status.status_code == 401

        res_result = await ac.get("/api/v1/tasks/test-task-123/result")
        assert res_result.status_code == 401


@pytest.mark.asyncio
async def test_submit_system_ping_endpoint_authenticated(
    app_instance, auth_context_tenant_a
) -> None:
    """Verify authenticated user can dispatch task and task service receives tenant context."""
    app_instance.dependency_overrides[require_authenticated_user] = lambda: auth_context_tenant_a

    mock_sub_res = TaskSubmissionResult(
        task_id="ping-task-uuid-1",
        status="PENDING",
        queue="default",
        duplicate=False,
    )

    with patch(
        "app.api.v1.tasks.task_service.submit_task",
        new=AsyncMock(return_value=mock_sub_res),
    ) as mock_submit:
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
        assert data["duplicate"] is False

        # Verify tenant_id and user_id were forwarded to service
        mock_submit.assert_called_once()
        call_kwargs = mock_submit.call_args.kwargs
        assert call_kwargs["tenant_id"] == TENANT_A
        assert call_kwargs["user_id"] == USER_A


@pytest.mark.asyncio
async def test_submit_system_ping_duplicate_idempotency(
    app_instance, auth_context_tenant_a
) -> None:
    """Verify duplicate submission returns duplicate: true flag with existing task ID."""
    app_instance.dependency_overrides[require_authenticated_user] = lambda: auth_context_tenant_a

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
async def test_cross_tenant_task_access_rejected(app_instance, auth_context_tenant_a) -> None:
    """Verify tenant isolation: User in Tenant A cannot read task created by Tenant B."""
    app_instance.dependency_overrides[require_authenticated_user] = lambda: auth_context_tenant_a

    # Simulate task belonging to Tenant B
    tenant_b_task_meta = {
        "task_id": "tenant-b-task",
        "tenant_id": str(TENANT_B),
        "user_id": str(USER_B),
    }

    with patch(
        "app.api.v1.tasks.task_service.get_task_metadata",
        new=AsyncMock(return_value=tenant_b_task_meta),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res_status = await ac.get("/api/v1/tasks/tenant-b-task/status")
            assert res_status.status_code == 403
            err_data = res_status.json()
            assert "Not authorized" in err_data["detail"]

            res_result = await ac.get("/api/v1/tasks/tenant-b-task/result")
            assert res_result.status_code == 403


@pytest.mark.asyncio
async def test_authorized_tenant_task_status_and_result(
    app_instance, auth_context_tenant_a
) -> None:
    """Verify user in Tenant A can successfully access task belonging to Tenant A."""
    app_instance.dependency_overrides[require_authenticated_user] = lambda: auth_context_tenant_a

    tenant_a_task_meta = {
        "task_id": "tenant-a-task",
        "tenant_id": str(TENANT_A),
        "user_id": str(USER_A),
    }

    mock_status = TaskStatusResult(
        task_id="tenant-a-task",
        status="SUCCESS",
        ready=True,
        successful=True,
        error=None,
        result={"status": "pong", "message": "hello"},
    )

    with (
        patch(
            "app.api.v1.tasks.task_service.get_task_metadata",
            new=AsyncMock(return_value=tenant_a_task_meta),
        ),
        patch(
            "app.api.v1.tasks.task_service.get_task_status",
            new=AsyncMock(return_value=mock_status),
        ),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            # Status check
            res_status = await ac.get("/api/v1/tasks/tenant-a-task/status")
            assert res_status.status_code == 200
            data = res_status.json()
            assert data["task_id"] == "tenant-a-task"
            assert data["status"] == "SUCCESS"
            assert data["successful"] is True

            # Result check
            res_result = await ac.get("/api/v1/tasks/tenant-a-task/result")
            assert res_result.status_code == 200
            result_data = res_result.json()
            assert result_data["result"] == {"status": "pong", "message": "hello"}


@pytest.mark.asyncio
async def test_non_existent_task_returns_404(app_instance, auth_context_tenant_a) -> None:
    """Verify querying unknown task with no metadata returns 404 Not Found."""
    app_instance.dependency_overrides[require_authenticated_user] = lambda: auth_context_tenant_a

    with patch(
        "app.api.v1.tasks.task_service.get_task_metadata",
        new=AsyncMock(return_value=None),
    ):
        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get("/api/v1/tasks/unknown-uuid/status")
            assert res.status_code == 404
