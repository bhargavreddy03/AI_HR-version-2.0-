"""Security foundation: Argon2id password hashing, SecurityContext, and PostgreSQL RLS tenant context."""

import logging
from uuid import UUID

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings, get_settings
from app.core.errors import AuthorizationException

logger = logging.getLogger(__name__)

_hasher: PasswordHasher | None = None


def get_password_hasher(settings: Settings | None = None) -> PasswordHasher:
    """Return configured Argon2id password hasher singleton adhering to AC-SEC-03 (memory >= 64MB)."""
    global _hasher
    if _hasher is None:
        cfg = settings or get_settings()
        _hasher = PasswordHasher(
            time_cost=cfg.ARGON2_TIME_COST,
            memory_cost=cfg.ARGON2_MEMORY_COST,
            parallelism=cfg.ARGON2_PARALLELISM,
            hash_len=cfg.ARGON2_HASH_LEN,
            salt_len=cfg.ARGON2_SALT_LEN,
            type=Type.ID,
        )
    return _hasher


def hash_password(plain_password: str, settings: Settings | None = None) -> str:
    """Hash plaintext password using Argon2id with memory cost >= 64MB."""
    hasher = get_password_hasher(settings=settings)
    return hasher.hash(plain_password)


def verify_password(
    plain_password: str, hashed_password: str, settings: Settings | None = None
) -> bool:
    """Verify plaintext password against stored Argon2id hash using constant-time comparison."""
    hasher = get_password_hasher(settings=settings)
    try:
        return hasher.verify(hashed_password, plain_password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(hashed_password: str, settings: Settings | None = None) -> bool:
    """Determine whether stored hash parameters have fallen behind current security standards."""
    hasher = get_password_hasher(settings=settings)
    try:
        return hasher.check_needs_rehash(hashed_password)
    except Exception:
        return True


# ------------------------------------------------------------------------------
# Security Context & Multi-Tenant RLS Integration
# ------------------------------------------------------------------------------


class TenantContext(BaseModel):
    """Verified tenant boundaries for multi-tenant PostgreSQL RLS context."""

    tenant_id: UUID = Field(..., description="Active verified organization identifier")
    is_active: bool = Field(default=True, description="Tenant active status")


class SecurityContext(BaseModel):
    """Authoritative security credentials and multi-tenant authorization context."""

    user_id: UUID = Field(..., description="Authenticated user UUID")
    session_id: UUID | None = Field(default=None, description="Active session UUID")
    tenant_id: UUID | None = Field(
        default=None, description="Active tenant UUID (if tenant-scoped request)"
    )
    roles: list[str] = Field(
        default_factory=list, description="Assigned roles within current tenant"
    )
    permissions: list[str] = Field(
        default_factory=list, description="Assigned capability codes within current tenant"
    )
    token_version: int = Field(default=1, description="Current user token epoch version")
    role_version: int = Field(default=1, description="Current organization membership role version")
    is_super_admin: bool = Field(default=False, description="Platform administrative flag")


async def set_tenant_context(session: AsyncSession, tenant_id: UUID) -> None:
    """Bind tenant identifier to the current PostgreSQL transaction for RLS evaluation.

    Executes `SELECT set_config('app.current_tenant_id', :tenant_id, true)` with `is_local = true`
    to guarantee strict transaction-scoped lifetime conforming to Architecture Document 04.
    """
    try:
        await session.execute(
            text("SELECT set_config('app.current_tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
    except Exception as exc:
        logger.error("Failed to set PostgreSQL RLS tenant context for %s: %s", tenant_id, exc)
        raise AuthorizationException("Failed to set tenant context boundary") from exc


# Dependency extension points for authentication and tenant isolation
async def get_security_context() -> SecurityContext | None:
    """Extension point: Return security context from request or None for public endpoints."""
    # Production token decoding and verification pipeline will be completed in Step 3.3
    return None


async def get_tenant_context() -> TenantContext | None:
    """Extension point: Return verified tenant context from request or None for global routes."""
    # Production tenant resolution pipeline will be completed in Step 3.3
    return None
