"""Organization membership, role assignment, and access control service layer.

Integrates server-side RBAC guards, Ceiling Rule, Sole Admin Protection, and Mass Assignment defense (Finding 5).
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.base import utc_now
from app.core.errors import AuthorizationException, EntityNotFoundException
from app.core.security.rbac import (
    PROTECTED_MEMBERSHIP_FIELDS,
    ROLE_ORG_ADMIN,
    ROLE_PLATFORM_SUPER_ADMIN,
    filter_mass_assignment_payload,
    validate_role_assignment,
    validate_sole_admin_protection,
)
from app.modules.organizations.models import OrganizationMembership, Role

logger = logging.getLogger(__name__)


async def assign_membership_role(
    db: AsyncSession,
    tenant_id: UUID,
    target_user_id: UUID,
    new_role_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
    actor_is_super_admin: bool = False,
) -> OrganizationMembership:
    """Assign or mutate an organization member's role with strict RBAC security guards.

    Enforces:
    1. Server-side authorization: Actor must be org_admin or platform_super_admin.
    2. Tenant isolation: The requested role must belong to tenant_id or be a platform system role.
    3. Ceiling Rule: Actor cannot grant roles or permissions higher than their authority.
    4. Super-Admin Protection: Org admins cannot grant platform_super_admin.
    5. Sole Admin Protection: The last active org admin cannot be demoted to a non-admin role.
    """
    # 1. Server-side authorization check
    if not actor_is_super_admin and actor_role not in (ROLE_ORG_ADMIN, ROLE_PLATFORM_SUPER_ADMIN):
        raise AuthorizationException(
            "Forbidden: Only organization administrators or super-administrators can assign roles",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # 2. Fetch the target role definition
    role_stmt = (
        select(Role).where(Role.id == new_role_id).options(selectinload(Role.role_permissions))
    )
    new_role = (await db.execute(role_stmt)).scalar_one_or_none()
    if not new_role:
        raise EntityNotFoundException("Role", new_role_id)

    # Cross-tenant role check: Role must be system or belong to this tenant
    if new_role.tenant_id is not None and new_role.tenant_id != tenant_id:
        raise AuthorizationException(
            "Security violation: Cannot assign a role belonging to another organization",
            error_code="CROSS_TENANT_ROLE_ASSIGNMENT",
        )

    # 3. Hierarchy and Ceiling Rule validation
    validate_role_assignment(
        actor_role=actor_role,
        target_role_name=new_role.name,
        actor_is_super_admin=actor_is_super_admin,
    )

    # 4. Fetch the existing membership
    mem_stmt = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.user_id == target_user_id,
        )
        .with_for_update()
    )
    membership = (await db.execute(mem_stmt)).scalar_one_or_none()
    if not membership:
        raise EntityNotFoundException("OrganizationMembership", f"{tenant_id}:{target_user_id}")

    # 5. Sole Admin Protection: Demotion check
    if new_role.name != ROLE_ORG_ADMIN:
        await validate_sole_admin_protection(db, tenant_id=tenant_id, target_user_id=target_user_id)

    # Apply role assignment and advance role version for cache invalidation
    membership.role_id = new_role.id
    membership.role_version += 1
    membership.updated_at = utc_now()
    await db.commit()
    await db.refresh(membership)

    logger.info(
        "Actor %s assigned role '%s' to user %s in tenant %s (role_version=%d)",
        actor_user_id,
        new_role.name,
        target_user_id,
        tenant_id,
        membership.role_version,
    )
    return membership


async def update_membership(
    db: AsyncSession,
    tenant_id: UUID,
    target_user_id: UUID,
    update_data: dict[str, Any],
    actor_user_id: UUID,
    actor_role: str,
    actor_is_super_admin: bool = False,
) -> OrganizationMembership:
    """Update organization membership details with mass-assignment defense and sole-admin protection.

    Enforces:
    1. Server-side authorization check.
    2. Mass assignment payload filtering: Strips immutable/structural fields (id, tenant_id, user_id, role_id, etc.).
    3. Sole Admin Protection: Deactivating the last active org admin is strictly rejected.
    """
    if not actor_is_super_admin and actor_role not in (ROLE_ORG_ADMIN, ROLE_PLATFORM_SUPER_ADMIN):
        raise AuthorizationException(
            "Forbidden: Only organization administrators can update memberships",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # Strip protected structural fields
    sanitized_fields = filter_mass_assignment_payload(update_data, PROTECTED_MEMBERSHIP_FIELDS)

    mem_stmt = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.user_id == target_user_id,
        )
        .with_for_update()
    )
    membership = (await db.execute(mem_stmt)).scalar_one_or_none()
    if not membership:
        raise EntityNotFoundException("OrganizationMembership", f"{tenant_id}:{target_user_id}")

    # Check for deactivation of sole admin
    if "is_active" in sanitized_fields and not sanitized_fields["is_active"]:
        await validate_sole_admin_protection(db, tenant_id=tenant_id, target_user_id=target_user_id)

    # Apply sanitized updates
    for field, val in sanitized_fields.items():
        if hasattr(membership, field):
            setattr(membership, field, val)

    membership.updated_at = utc_now()
    await db.commit()
    await db.refresh(membership)
    return membership


async def remove_membership(
    db: AsyncSession,
    tenant_id: UUID,
    target_user_id: UUID,
    actor_user_id: UUID,
    actor_role: str,
    actor_is_super_admin: bool = False,
) -> bool:
    """Remove a user membership from an organization with sole-admin protection.

    Enforces:
    1. Server-side authorization check.
    2. Sole Admin Protection: Removing the last active org admin is rejected.
    """
    if not actor_is_super_admin and actor_role not in (ROLE_ORG_ADMIN, ROLE_PLATFORM_SUPER_ADMIN):
        raise AuthorizationException(
            "Forbidden: Only organization administrators can remove memberships",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # Ensure this removal does not leave the tenant without an active admin
    await validate_sole_admin_protection(db, tenant_id=tenant_id, target_user_id=target_user_id)

    mem_stmt = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.user_id == target_user_id,
        )
        .with_for_update()
    )
    membership = (await db.execute(mem_stmt)).scalar_one_or_none()
    if not membership:
        raise EntityNotFoundException("OrganizationMembership", f"{tenant_id}:{target_user_id}")

    await db.delete(membership)
    await db.commit()
    return True
