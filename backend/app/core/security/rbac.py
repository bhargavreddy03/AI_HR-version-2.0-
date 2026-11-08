"""Centralized Role-Based Access Control (RBAC), privilege escalation prevention, and IDOR defense.

Enforces Ceiling Rule, Sole Admin Protection, and resource ownership conforming to Architecture Document 08 and Section 4.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AuthorizationException

logger = logging.getLogger(__name__)

# Standard System Roles approved in Architecture Document 08
ROLE_CANDIDATE = "candidate"
ROLE_RECRUITER = "recruiter"
ROLE_HIRING_MANAGER = "hiring_manager"
ROLE_ORG_ADMIN = "org_admin"
ROLE_PLATFORM_SUPER_ADMIN = "platform_super_admin"

# Hierarchical authority ranking for system roles
ROLE_HIERARCHY: dict[str, int] = {
    ROLE_PLATFORM_SUPER_ADMIN: 100,
    ROLE_ORG_ADMIN: 50,
    ROLE_HIRING_MANAGER: 20,
    ROLE_RECRUITER: 20,
    ROLE_CANDIDATE: 10,
}

# Fields strictly forbidden from being updated via standard user-facing API payloads
PROTECTED_USER_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "is_super_admin",
        "token_version",
        "password_hash",
        "mfa_secret",
        "mfa_backup_codes",
        "created_at",
        "updated_at",
    }
)

PROTECTED_MEMBERSHIP_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "tenant_id",
        "user_id",
        "role_id",
        "role_version",
        "created_at",
        "updated_at",
    }
)


def has_permission(
    granted_permissions: list[str],
    required_permission: str,
    is_super_admin: bool = False,
) -> bool:
    """Evaluate whether granted permissions satisfy the required capability code.

    Deny-by-default evaluation supporting exact match and module-level wildcards (e.g. 'jobs:*').
    """
    if is_super_admin:
        return True

    if required_permission in granted_permissions:
        return True

    # Check wildcard pattern matching (e.g., 'jobs:*' covers 'jobs:read')
    module = required_permission.split(":", 1)[0]
    if (
        f"{module}:*" in granted_permissions
        or "*:*" in granted_permissions
        or "*" in granted_permissions
    ):
        return True

    return False


def validate_ceiling_rule(
    assigner_permissions: set[str],
    requested_permissions: set[str],
    is_super_admin: bool = False,
) -> None:
    """Enforce Ceiling Rule: An administrator cannot grant capabilities they do not possess.

    Raises:
        AuthorizationException: If privilege escalation is attempted.
    """
    if is_super_admin:
        return

    unauthorized_grants = requested_permissions - assigner_permissions
    if unauthorized_grants:
        logger.warning(
            "Privilege escalation attempt detected. Unauthorized requested capabilities: %s",
            unauthorized_grants,
        )
        raise AuthorizationException(
            f"Privilege escalation blocked: Cannot grant capabilities you do not possess: {', '.join(sorted(unauthorized_grants))}",
            error_code="PRIVILEGE_ESCALATION_BLOCKED",
        )


def validate_role_assignment(
    actor_role: str,
    target_role_name: str,
    actor_is_super_admin: bool = False,
    actor_permissions: set[str] | None = None,
    target_permissions: set[str] | None = None,
) -> None:
    """Validate that the actor has authority to grant the target role or permissions.

    Enforces:
    1. Only platform super-admins can grant platform super-admin privileges.
    2. An actor cannot grant a role higher in the hierarchy than their own.
    3. Ceiling Rule: An actor cannot grant permissions exceeding their own capabilities.
    """
    if actor_is_super_admin or actor_role == ROLE_PLATFORM_SUPER_ADMIN:
        return

    # 1. Organization administrators and below cannot grant platform super-admin privileges
    if target_role_name == ROLE_PLATFORM_SUPER_ADMIN:
        logger.warning(
            "Privilege escalation attempt: Actor with role '%s' attempted to grant '%s'",
            actor_role,
            ROLE_PLATFORM_SUPER_ADMIN,
        )
        raise AuthorizationException(
            "Privilege escalation blocked: Organization administrators cannot grant platform super-admin privileges",
            error_code="SUPER_ADMIN_GRANT_PROHIBITED",
        )

    # 2. Hierarchy ceiling check
    actor_level = ROLE_HIERARCHY.get(actor_role, 0)
    target_level = ROLE_HIERARCHY.get(target_role_name, 0)
    if target_level > actor_level:
        logger.warning(
            "Privilege escalation attempt: Actor level %d (%s) attempted to assign role level %d (%s)",
            actor_level,
            actor_role,
            target_level,
            target_role_name,
        )
        raise AuthorizationException(
            f"Privilege escalation blocked: Cannot grant role '{target_role_name}' which exceeds your authority level",
            error_code="PRIVILEGE_ESCALATION_BLOCKED",
        )

    # 3. Fine-grained permission ceiling check if permissions are provided
    if actor_permissions is not None and target_permissions is not None:
        validate_ceiling_rule(
            actor_permissions, target_permissions, is_super_admin=actor_is_super_admin
        )


async def validate_sole_admin_protection(
    db: AsyncSession,
    tenant_id: UUID,
    target_user_id: UUID,
) -> None:
    """Ensure an organization cannot be left without at least one active administrator.

    Raises:
        AuthorizationException: If target_user_id is the sole active admin and is being deactivated or demoted.
    """
    from app.modules.organizations.models import OrganizationMembership, Role

    # Count active org_admin memberships for this tenant
    stmt = (
        select(func.count(OrganizationMembership.id))
        .join(Role, Role.id == OrganizationMembership.role_id)
        .where(
            OrganizationMembership.tenant_id == tenant_id,
            OrganizationMembership.is_active.is_(True),
            Role.name == ROLE_ORG_ADMIN,
        )
    )
    admin_count = (await db.execute(stmt)).scalar() or 0

    if admin_count <= 1:
        # Check if the target user is currently an active org_admin
        target_stmt = (
            select(OrganizationMembership.id)
            .join(Role, Role.id == OrganizationMembership.role_id)
            .where(
                OrganizationMembership.tenant_id == tenant_id,
                OrganizationMembership.user_id == target_user_id,
                OrganizationMembership.is_active.is_(True),
                Role.name == ROLE_ORG_ADMIN,
            )
        )
        is_target_admin = (await db.execute(target_stmt)).scalar_one_or_none()
        if is_target_admin is not None:
            raise AuthorizationException(
                "Operation rejected: Cannot deactivate or remove the sole administrator of an active organization",
                error_code="SOLE_ADMIN_PROTECTION_VIOLATION",
            )


def assert_tenant_ownership(
    resource_tenant_id: UUID | str | None,
    current_tenant_id: UUID | str | None,
) -> None:
    """Enforce cross-tenant boundary isolation and prevent Insecure Direct Object Reference (IDOR).

    Raises:
        AuthorizationException: If resource belongs to another organization.
    """
    if not resource_tenant_id or not current_tenant_id:
        raise AuthorizationException(
            "Tenant context is required to access organization resources",
            error_code="TENANT_CONTEXT_REQUIRED",
        )
    if str(resource_tenant_id) != str(current_tenant_id):
        logger.warning(
            "Cross-tenant IDOR attempt blocked: caller tenant %s tried to access resource of tenant %s",
            current_tenant_id,
            resource_tenant_id,
        )
        raise AuthorizationException(
            "Access denied: Requested resource does not belong to your organization",
            error_code="CROSS_TENANT_ACCESS_DENIED",
        )


def assert_user_ownership(
    resource_user_id: UUID | str,
    current_user_id: UUID | str,
    is_admin_override: bool = False,
) -> None:
    """Enforce user self-ownership on personal resources (e.g. Candidate Profile, User Credentials).

    Raises:
        AuthorizationException: If resource belongs to another user.
    """
    if is_admin_override:
        return
    if str(resource_user_id) != str(current_user_id):
        raise AuthorizationException(
            "Access denied: You do not have permission to access another user's personal resource",
            error_code="USER_RESOURCE_ACCESS_DENIED",
        )


def filter_mass_assignment_payload(
    payload: dict[str, Any],
    protected_fields: frozenset[str],
) -> dict[str, Any]:
    """Filter out protected structural fields from user-provided update dictionaries."""
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key in protected_fields:
            logger.warning("Stripped protected field '%s' from API update payload", key)
            continue
        sanitized[key] = value
    return sanitized
