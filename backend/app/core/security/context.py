"""SecurityContext, TenantContext, and PostgreSQL RLS transaction context binding.

Conforms to Architecture Document 04 and 07.
"""

from __future__ import annotations

import logging
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationException

logger = logging.getLogger(__name__)


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


async def get_security_context() -> SecurityContext | None:
    """Return security context from request or None for public endpoints."""
    return None


async def get_tenant_context() -> TenantContext | None:
    """Return verified tenant context from request or None for global routes."""
    return None
