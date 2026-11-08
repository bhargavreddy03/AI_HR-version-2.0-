"""Organization membership, role assignment, and access control service layer.

Integrates server-side RBAC guards, Ceiling Rule, Sole Admin Protection, Mass Assignment defense,
and concurrency serialization (Findings 2 & 3).
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
from app.modules.auth.models import User
from app.modules.organizations.models import (
    Organization,
    OrganizationMembership,
    Role,
    RolePermission,
)

logger = logging.getLogger(__name__)


async def serialize_organization_mutation(db: AsyncSession, tenant_id: UUID) -> None:
    """Serialize administrator demotion, deactivation, and removal operations per organization.

    Acquires an exclusive row-level lock on the Organization record, ensuring that
    admin counting, role validation, and membership mutations occur sequentially
    within the same database transaction (Finding 2).
    """
    org_stmt = select(Organization.id).where(Organization.id == tenant_id).with_for_update()
    org_res = (await db.execute(org_stmt)).scalar_one_or_none()
    if org_res is None:
        raise EntityNotFoundException("Organization", tenant_id)


async def _resolve_trusted_actor_context(
    db: AsyncSession,
    tenant_id: UUID,
    actor_user_id: UUID,
) -> tuple[str, bool, set[str]]:
    """Resolve actor role, super-admin status, and permission codes from trusted database records.

    Never relies on caller-supplied claims or parameters (Finding 3).

    Returns:
        tuple[actor_role_name, is_super_admin, actor_permissions_set]
    """
    user_stmt = select(User).where(User.id == actor_user_id)
    actor_user = (await db.execute(user_stmt)).scalar_one_or_none()
    if not actor_user or not getattr(actor_user, "is_active", False):
        logger.warning("Actor %s is unknown or inactive in database", actor_user_id)
        raise AuthorizationException(
            "Forbidden: Invalid or inactive actor account",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    if getattr(actor_user, "is_super_admin", False):
        return ROLE_PLATFORM_SUPER_ADMIN, True, set()

    mem_stmt = (
        select(OrganizationMembership)
        .where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.user_id == actor_user_id,
            OrganizationMembership.is_active.is_(True),
        )
        .options(
            selectinload(OrganizationMembership.role)
            .selectinload(Role.role_permissions)
            .selectinload(RolePermission.permission)
        )
    )
    actor_mem = (await db.execute(mem_stmt)).scalar_one_or_none()
    if not actor_mem or not actor_mem.role:
        logger.warning(
            "Actor %s does not have an active membership in tenant %s",
            actor_user_id,
            tenant_id,
        )
        raise AuthorizationException(
            "Forbidden: You are not an active member of this organization",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    actor_role_name = actor_mem.role.name
    actor_permissions = {
        rp.permission.code
        for rp in actor_mem.role.role_permissions
        if rp.permission and rp.permission.code
    }
    return actor_role_name, False, actor_permissions


async def assign_membership_role(
    db: AsyncSession,
    tenant_id: UUID,
    target_user_id: UUID,
    new_role_id: UUID,
    actor_user_id: UUID,
    actor_role: str | None = None,
    actor_is_super_admin: bool | None = None,
) -> OrganizationMembership:
    """Assign or mutate an organization member's role with strict RBAC security guards.

    Enforces:
    1. Server-side authorization: Actor must be org_admin or platform_super_admin (resolved from DB).
    2. Concurrency Serialization: Operations are serialized per tenant organization row lock.
    3. Tenant isolation: The requested role must belong to tenant_id or be a platform system role.
    4. Ceiling Rule: Actor cannot grant roles or permissions higher than their authority (resolved from DB).
    5. Super-Admin Protection: Org admins cannot grant platform_super_admin.
    6. Sole Admin Protection: The last active org admin cannot be demoted to a non-admin role.
    """
    # 1. Resolve actor authority and permissions exclusively from trusted database records (Finding 3)
    resolved_role, is_super_admin, actor_permissions = await _resolve_trusted_actor_context(
        db, tenant_id=tenant_id, actor_user_id=actor_user_id
    )

    if not is_super_admin and resolved_role != ROLE_ORG_ADMIN:
        raise AuthorizationException(
            "Forbidden: Only organization administrators or super-administrators can assign roles",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # 2. Serialize administrator mutations per organization within this transaction (Finding 2)
    await serialize_organization_mutation(db, tenant_id)

    # 3. Fetch the target role definition with its permissions from trusted database records
    role_stmt = (
        select(Role)
        .where(Role.id == new_role_id)
        .options(selectinload(Role.role_permissions).selectinload(RolePermission.permission))
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

    target_permissions = {
        rp.permission.code
        for rp in new_role.role_permissions
        if rp.permission and rp.permission.code
    }

    # 4. Hierarchy and Ceiling Rule validation using DB-resolved permissions
    validate_role_assignment(
        actor_role=resolved_role,
        target_role_name=new_role.name,
        actor_is_super_admin=is_super_admin,
        actor_permissions=actor_permissions if not is_super_admin else None,
        target_permissions=target_permissions if not is_super_admin else None,
    )

    # 5. Fetch the existing membership with row-level lock
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

    # 6. Sole Admin Protection: Demotion check executed within the serialized transaction
    if new_role.name != ROLE_ORG_ADMIN:
        await validate_sole_admin_protection(
            db, tenant_id=tenant_id, target_user_id=target_user_id, serialize=False
        )

    # 7. Apply role assignment and advance role version for cache invalidation within same transaction
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
    actor_role: str | None = None,
    actor_is_super_admin: bool | None = None,
) -> OrganizationMembership:
    """Update organization membership details with mass-assignment defense and sole-admin protection.

    Enforces:
    1. Server-side authorization check resolved from database.
    2. Concurrency Serialization: Operations are serialized per tenant organization row lock.
    3. Mass assignment payload filtering: Strips immutable/structural fields.
    4. Sole Admin Protection: Deactivating the last active org admin is strictly rejected.
    """
    resolved_role, is_super_admin, _ = await _resolve_trusted_actor_context(
        db, tenant_id=tenant_id, actor_user_id=actor_user_id
    )
    if not is_super_admin and resolved_role != ROLE_ORG_ADMIN:
        raise AuthorizationException(
            "Forbidden: Only organization administrators can update memberships",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # Serialize mutations per organization within this transaction (Finding 2)
    await serialize_organization_mutation(db, tenant_id)

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

    # Check for deactivation of sole admin within the same serialized transaction
    if "is_active" in sanitized_fields and not sanitized_fields["is_active"]:
        await validate_sole_admin_protection(
            db, tenant_id=tenant_id, target_user_id=target_user_id, serialize=False
        )

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
    actor_role: str | None = None,
    actor_is_super_admin: bool | None = None,
) -> bool:
    """Remove a user membership from an organization with sole-admin protection.

    Enforces:
    1. Server-side authorization check resolved from database.
    2. Concurrency Serialization: Operations are serialized per tenant organization row lock.
    3. Sole Admin Protection: Removing the last active org admin is rejected.
    """
    resolved_role, is_super_admin, _ = await _resolve_trusted_actor_context(
        db, tenant_id=tenant_id, actor_user_id=actor_user_id
    )
    if not is_super_admin and resolved_role != ROLE_ORG_ADMIN:
        raise AuthorizationException(
            "Forbidden: Only organization administrators can remove memberships",
            error_code="MEMBERSHIP_MUTATION_FORBIDDEN",
        )

    # Serialize mutations per organization within this transaction (Finding 2)
    await serialize_organization_mutation(db, tenant_id)

    # Ensure this removal does not leave the tenant without an active admin within the same transaction
    await validate_sole_admin_protection(
        db, tenant_id=tenant_id, target_user_id=target_user_id, serialize=False
    )

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
