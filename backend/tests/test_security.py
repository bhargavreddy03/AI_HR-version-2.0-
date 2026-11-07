"""Test suite for security foundation: Argon2id password hashing, SecurityContext, and tenant boundaries."""

import uuid
from unittest.mock import AsyncMock

import pytest

from app.core.errors import AuthorizationException
from app.core.security import (
    SecurityContext,
    TenantContext,
    hash_password,
    needs_rehash,
    set_tenant_context,
    verify_password,
)


def test_argon2id_hashing_and_verification() -> None:
    """Verify that hash_password produces valid Argon2id hashes verified by verify_password."""
    password = "SuperSecretPassword123!#"
    hashed = hash_password(password)

    # Assert hash structure adheres to Argon2id specification
    assert hashed.startswith("$argon2id$")
    assert "m=65536" in hashed  # Enforces AC-SEC-03: memory_cost >= 64MB

    # Verify correct password succeeds
    assert verify_password(password, hashed) is True

    # Verify incorrect password fails
    assert verify_password("WrongPassword456!#", hashed) is False

    # Verify corrupted hash fails gracefully without raising uncaught errors
    assert verify_password(password, "invalid_corrupted_hash") is False


def test_argon2id_needs_rehash() -> None:
    """Verify that freshly hashed password does not need rehash under current settings."""
    hashed = hash_password("TestPassword123!")
    assert needs_rehash(hashed) is False


def test_tenant_context_and_security_context_models() -> None:
    """Verify TenantContext and SecurityContext Pydantic data models."""
    org_id = uuid.uuid4()
    user_id = uuid.uuid4()

    tenant_ctx = TenantContext(tenant_id=org_id, is_active=True)
    assert tenant_ctx.tenant_id == org_id
    assert tenant_ctx.is_active is True

    security_ctx = SecurityContext(
        user_id=user_id,
        tenant_id=org_id,
        roles=["recruiter", "hiring_manager"],
        token_version=2,
        role_version=1,
        is_super_admin=False,
    )
    assert security_ctx.user_id == user_id
    assert security_ctx.roles == ["recruiter", "hiring_manager"]
    assert security_ctx.token_version == 2


@pytest.mark.asyncio
async def test_set_tenant_context_executes_transaction_scoped_config() -> None:
    """Verify that set_tenant_context executes transaction-local set_config (is_local=true)."""
    mock_session = AsyncMock()
    tenant_id = uuid.uuid4()

    await set_tenant_context(mock_session, tenant_id)

    mock_session.execute.assert_called_once()
    args, kwargs = mock_session.execute.call_args
    assert "SELECT set_config('app.current_tenant_id', :tenant_id, true)" in str(args[0])
    # Parameter is passed in dictionary as second positional argument or keyword argument
    params = kwargs if "tenant_id" in kwargs else args[1]
    assert params["tenant_id"] == str(tenant_id)


@pytest.mark.asyncio
async def test_set_tenant_context_raises_authorization_exception_on_failure() -> None:
    """Verify that failure during set_config raises an AuthorizationException."""
    mock_session = AsyncMock()
    mock_session.execute.side_effect = RuntimeError("Connection dropped")

    with pytest.raises(AuthorizationException):
        await set_tenant_context(mock_session, uuid.uuid4())
