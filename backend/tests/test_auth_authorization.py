"""Unit tests for multi-tenant authorization, version fences, RBAC dependencies, and fail-closed behaviors."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import APIRouter, Depends, status
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.database import get_db
from app.core.redis import get_redis_client
from app.core.security import SecurityContext, TenantContext
from app.main import create_application
from app.modules.auth.dependencies import (
    get_app_redis,
    require_active_tenant,
    require_permission,
    require_role,
)
from app.modules.auth.jwt import COOKIE_ACCESS, COOKIE_CSRF, create_access_token
from app.modules.auth.models import User
from app.modules.organizations.models import Organization, OrganizationMembership, Role
from tests.test_auth_api import FakeRedis


@pytest.fixture
def authz_app() -> tuple[TestClient, AsyncMock, FakeRedis, Settings]:
    test_settings = Settings(
        ENVIRONMENT="testing",
        DEBUG=True,
        JWT_SECRET_KEY="test_jwt_secret_key_minimum_32_characters_for_testing_suite",
        POSTGRES_PASSWORD="test_database_password_only",
        REDIS_URL="redis://localhost:6379/15",
        COOKIE_SECURE=False,
    )
    app = create_application(settings=test_settings)
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    fake_redis = FakeRedis()

    app.state.redis_client = fake_redis
    app.dependency_overrides[get_db] = lambda: mock_db
    app.dependency_overrides[get_app_redis] = lambda: fake_redis
    app.dependency_overrides[get_redis_client] = lambda: fake_redis

    # Mount test protected routes
    test_router = APIRouter(prefix="/test-protected")

    @test_router.get("/tenant-only")
    async def tenant_only(
        tenant_ctx: TenantContext = Depends(require_active_tenant),
    ) -> dict[str, str]:
        return {"status": "ok", "tenant_id": str(tenant_ctx.tenant_id)}

    @test_router.get("/permission-jobs-create")
    async def jobs_create_only(
        sec_ctx: SecurityContext = Depends(require_permission("jobs:create")),
    ) -> dict[str, str]:
        return {"status": "ok"}

    @test_router.get("/role-recruiter-only")
    async def recruiter_only(
        sec_ctx: SecurityContext = Depends(require_role("recruiter")),
    ) -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(test_router)
    client = TestClient(app)
    return client, mock_db, fake_redis, test_settings


def test_permission_dependency_enforces_capability_code(
    authz_app: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that require_permission grants access when code is present and raises 403 when absent."""
    client, _, fake_redis, settings = authz_app

    user_id = uuid4()
    session_id = uuid4()
    tenant_id = uuid4()

    # 1. Token with jobs:create -> 200 OK
    token_valid = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        role="recruiter",
        permissions=["jobs:create"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )

    fake_redis.store[f"session:{user_id}:{session_id}"] = (
        f'{{"token_version": 1, "role_version": 1, "last_db_verified_at": {datetime.now(UTC).timestamp()}}}'
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "1"
    fake_redis.store[f"org_current_role_version:{tenant_id}:{user_id}"] = "1"

    client.cookies.set(COOKIE_ACCESS, token_valid)
    res_ok = client.get("/test-protected/permission-jobs-create")
    assert res_ok.status_code == status.HTTP_200_OK

    # 2. Token without jobs:create -> 403 Forbidden
    token_unauth = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=tenant_id,
        role="hiring_manager",
        permissions=["screening:view"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    client.cookies.set(COOKIE_ACCESS, token_unauth)
    res_forbidden = client.get("/test-protected/permission-jobs-create")
    assert res_forbidden.status_code == status.HTTP_403_FORBIDDEN
    assert res_forbidden.json()["code"] == "PERMISSION_DENIED"


def test_exact_version_fence_invariant_stale_token_rejected(
    authz_app: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify that a stale token (< current version fence) is rejected with 401 Unauthorized."""
    client, _, fake_redis, settings = authz_app

    user_id = uuid4()
    session_id = uuid4()

    # Token has version 1
    token_v1 = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=[],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )

    # Redis version fence has advanced to 2 (e.g., following a password reset)
    fake_redis.store[f"session:{user_id}:{session_id}"] = (
        f'{{"token_version": 2, "role_version": 1, "last_db_verified_at": {datetime.now(UTC).timestamp()}}}'
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "2"

    client.cookies.set(COOKIE_ACCESS, token_v1)
    res = client.get("/test-protected/tenant-only")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "TOKEN_VERSION_STALE"


def test_state_b_reachable_cache_miss_strictly_rejects(
    authz_app: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """State B: When Redis is reachable but session key is absent, strictly reject without querying DB."""
    client, mock_db, fake_redis, settings = authz_app

    user_id = uuid4()
    session_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=None,
        role="candidate",
        permissions=[],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )

    client.cookies.set(COOKIE_ACCESS, token)
    # Session key absent in fake_redis

    res = client.get("/test-protected/tenant-only")
    assert res.status_code == status.HTTP_401_UNAUTHORIZED
    assert res.json()["code"] == "SESSION_REVOKED_OR_EXPIRED"
    # Assert DB was NOT queried (Strict Negative Assertion rule)
    assert not mock_db.execute.called


def test_switch_organization_protocol(
    authz_app: tuple[TestClient, AsyncMock, FakeRedis, Settings],
) -> None:
    """Verify organization switching adheres to Architecture Document 07 Section 7."""
    client, mock_db, fake_redis, settings = authz_app

    user_id = uuid4()
    session_id = uuid4()
    initial_tenant_id = uuid4()
    target_tenant_id = uuid4()

    token = create_access_token(
        user_id=user_id,
        session_id=session_id,
        tenant_id=initial_tenant_id,
        role="recruiter",
        permissions=["jobs:create"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
        settings=settings,
    )
    client.cookies.set(COOKIE_ACCESS, token)
    client.cookies.set(COOKIE_CSRF, "csrf_123")

    fake_redis.store[f"session:{user_id}:{session_id}"] = (
        f'{{"token_version": 1, "role_version": 1, "last_db_verified_at": {datetime.now(UTC).timestamp()}}}'
    )
    fake_redis.store[f"user_current_token_version:{user_id}"] = "1"
    fake_redis.store[f"org_current_role_version:{initial_tenant_id}:{user_id}"] = "1"

    # Mock DB entities for target organization
    target_org = Organization(
        id=target_tenant_id,
        name="Target Corp",
        slug="target-corp",
        status="active",
    )
    role = Role(
        id=uuid4(),
        name="org_admin",
        is_system=True,
    )
    membership = OrganizationMembership(
        id=uuid4(),
        tenant_id=target_tenant_id,
        user_id=user_id,
        role_id=role.id,
        is_active=True,
        role_version=1,
    )
    membership.role = role

    user = User(
        id=user_id,
        email="multi_tenant@example.com",
        password_hash="hash",
        first_name="Multi",
        last_name="Tenant",
        is_active=True,
        mfa_enabled=False,
        token_version=1,
    )

    def mock_execute(stmt: Any, *args: Any, **kwargs: Any) -> MagicMock:
        stmt_str = str(stmt)
        res = MagicMock()
        if "set_config" in stmt_str:
            return res
        if "organizations" in stmt_str:
            res.scalar_one_or_none.return_value = target_org
            return res
        if "organization_memberships" in stmt_str:
            res.scalar_one_or_none.return_value = membership
            return res
        if "permissions" in stmt_str or "role_permissions" in stmt_str:
            res.scalars.return_value.all.return_value = ["org:manage"]
            return res
        if "users" in stmt_str:
            res.scalar_one.return_value = user
            res.scalar_one_or_none.return_value = user
            return res
        if "user_sessions" in stmt_str:
            res.scalar_one_or_none.return_value = None
            return res
        return res

    mock_db.execute = AsyncMock(side_effect=mock_execute)

    res = client.post(
        "/api/v1/auth/switch-organization",
        json={"target_tenant_id": str(target_tenant_id)},
        headers={"X-CSRF-Token": "csrf_123"},
    )
    assert res.status_code == status.HTTP_200_OK
    data = res.json()
    assert data["user"]["active_tenant_id"] == str(target_tenant_id)
    assert data["user"]["role"] == "org_admin"
    assert COOKIE_ACCESS in res.cookies
