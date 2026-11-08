"""Initial authentication, identity, tenancy, and revocation schema (Step 3.3).

Revision ID: 001_auth_identity
Revises: None
Create Date: 2026-11-07 21:55:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001_auth_identity"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Platform-Global Root: organizations
    # --------------------------------------------------------------------------
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="active"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("slug", name="uq_organizations_slug"),
    )
    op.create_index("ix_organizations_slug", "organizations", ["slug"])

    # --------------------------------------------------------------------------
    # 2. Platform-Global Identity Anchor: users
    # --------------------------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("last_name", sa.String(100), nullable=False),
        sa.Column("phone_number", sa.String(30), nullable=True),
        sa.Column("avatar_url", sa.String(512), nullable=True),
        sa.Column("mfa_secret", sa.String(512), nullable=True),
        sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("mfa_backup_codes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("oauth_provider", sa.String(50), nullable=True),
        sa.Column("oauth_subject_id", sa.String(255), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("is_super_admin", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("litigation_hold", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "force_authoritative_check",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
        ),
        sa.Column("last_login_ip", sa.String(45), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint(
            "length(trim(first_name)) > 0 AND length(trim(last_name)) > 0",
            name="chk_users_names",
        ),
    )
    op.create_index("ix_users_email", "users", ["email"])

    # --------------------------------------------------------------------------
    # 3. Candidate-Owned Global Profile: candidate_user_profiles
    # --------------------------------------------------------------------------
    op.create_table(
        "candidate_user_profiles",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("headline", sa.String(255), nullable=True),
        sa.Column("bio", sa.Text(), nullable=True),
        sa.Column(
            "portfolio_urls",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "self_declared_skills",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    # --------------------------------------------------------------------------
    # 4. Roles (System & Tenant-Custom): roles
    # --------------------------------------------------------------------------
    op.create_table(
        "roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("tenant_id", "name", name="uq_roles_tenant_id_name"),
    )
    op.create_index("ix_roles_name", "roles", ["name"])
    op.create_index("ix_roles_tenant_id", "roles", ["tenant_id"])

    # --------------------------------------------------------------------------
    # 5. Global Capability Codes: permissions
    # --------------------------------------------------------------------------
    op.create_table(
        "permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("module", sa.String(50), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint("code", name="uq_permissions_code"),
    )
    op.create_index("ix_permissions_code", "permissions", ["code"])
    op.create_index("ix_permissions_module", "permissions", ["module"])

    # --------------------------------------------------------------------------
    # 6. Role Permissions Mapping: role_permissions
    # --------------------------------------------------------------------------
    op.create_table(
        "role_permissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "permission_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("permissions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "role_id", "permission_id", name="uq_role_permissions_role_id_permission_id"
        ),
    )
    op.create_index("ix_role_permissions_role_id", "role_permissions", ["role_id"])
    op.create_index("ix_role_permissions_permission_id", "role_permissions", ["permission_id"])

    # --------------------------------------------------------------------------
    # 7. Tenant-Scoped Memberships: organization_memberships (Tenant-Scoped Table 1)
    # --------------------------------------------------------------------------
    op.create_table(
        "organization_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("roles.id"),
            nullable=False,
        ),
        sa.Column("department_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("role_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.UniqueConstraint(
            "tenant_id", "user_id", name="uq_organization_memberships_tenant_id_user_id"
        ),
    )
    op.create_index(
        "ix_organization_memberships_tenant_id", "organization_memberships", ["tenant_id"]
    )
    op.create_index("ix_organization_memberships_user_id", "organization_memberships", ["user_id"])
    op.create_index("ix_organization_memberships_role_id", "organization_memberships", ["role_id"])

    # Enable and Force PostgreSQL Row-Level Security (RLS) on Tenant-Scoped Table 1
    op.execute("ALTER TABLE organization_memberships ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE organization_memberships FORCE ROW LEVEL SECURITY;")
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_policies
                WHERE tablename = 'organization_memberships' AND policyname = 'org_mem_tenant_restrict'
            ) THEN
                CREATE POLICY org_mem_tenant_restrict ON organization_memberships
                FOR ALL
                USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
            END IF;
        END $$;
    """)

    # Enforce Tenant-Role Integrity: A membership cannot reference another tenant's custom role
    op.execute("""
        CREATE OR REPLACE FUNCTION fn_enforce_membership_role_tenant()
        RETURNS trigger AS $$
        DECLARE
            v_role_tenant_id uuid;
            v_is_system boolean;
        BEGIN
            SELECT tenant_id, is_system INTO v_role_tenant_id, v_is_system
            FROM roles WHERE id = NEW.role_id;

            IF NOT FOUND THEN
                RAISE EXCEPTION 'Role % does not exist', NEW.role_id;
            END IF;

            IF NOT v_is_system AND (v_role_tenant_id IS NULL OR v_role_tenant_id != NEW.tenant_id) THEN
                RAISE EXCEPTION 'Cross-tenant role assignment prohibited: Role % does not belong to tenant %', NEW.role_id, NEW.tenant_id
                    USING ERRCODE = 'check_violation';
            END IF;

            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute(
        "DROP TRIGGER IF EXISTS trg_enforce_membership_role_tenant ON organization_memberships;"
    )
    op.execute("""
        CREATE TRIGGER trg_enforce_membership_role_tenant
            BEFORE INSERT OR UPDATE OF tenant_id, role_id ON organization_memberships
            FOR EACH ROW
            EXECUTE FUNCTION fn_enforce_membership_role_tenant();
    """)

    # --------------------------------------------------------------------------
    # 8. User Sessions Registry: user_sessions
    # --------------------------------------------------------------------------
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("refresh_token_hash", sa.String(255), nullable=False),
        sa.Column("previous_refresh_token_hash", sa.String(255), nullable=True),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("is_revoked", sa.Boolean(), nullable=False, server_default=sa.text("FALSE")),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_index("ix_user_sessions_tenant_id", "user_sessions", ["tenant_id"])
    op.create_index("ix_user_sessions_refresh_token_hash", "user_sessions", ["refresh_token_hash"])
    op.create_index(
        "ix_user_sessions_previous_refresh_token_hash",
        "user_sessions",
        ["previous_refresh_token_hash"],
    )
    op.create_index("ix_user_sessions_is_revoked", "user_sessions", ["is_revoked"])
    op.create_index("ix_user_sessions_expires_at", "user_sessions", ["expires_at"])

    # --------------------------------------------------------------------------
    # 8b. Session Token History (Full Session Lifetime Reuse Detection)
    # --------------------------------------------------------------------------
    op.create_table(
        "session_token_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("user_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.create_index("ix_session_token_history_session_id", "session_token_history", ["session_id"])
    op.create_index("ix_session_token_history_token_hash", "session_token_history", ["token_hash"])

    # --------------------------------------------------------------------------
    # 9. Transactional Invalidation Outbox: auth_revocation_outbox
    # --------------------------------------------------------------------------
    op.create_table(
        "auth_revocation_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("new_version", sa.Integer(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_auth_revocation_outbox_event_type", "auth_revocation_outbox", ["event_type"]
    )
    op.create_index("ix_auth_revocation_outbox_entity_id", "auth_revocation_outbox", ["entity_id"])
    op.create_index("ix_auth_revocation_outbox_user_id", "auth_revocation_outbox", ["user_id"])
    op.create_index(
        "ix_auth_revocation_outbox_organization_id", "auth_revocation_outbox", ["organization_id"]
    )
    op.create_index(
        "ix_auth_revocation_outbox_created_at", "auth_revocation_outbox", ["created_at"]
    )
    op.create_index(
        "ix_auth_revocation_outbox_processed_at", "auth_revocation_outbox", ["processed_at"]
    )

    # --------------------------------------------------------------------------
    # 10. Seed Platform-Global System Roles & Capabilities
    # --------------------------------------------------------------------------
    from app.core.base import generate_uuid7

    # System roles
    roles_data = [
        {
            "id": generate_uuid7(),
            "name": "candidate",
            "description": "Direct job applicant",
            "is_system": True,
        },
        {
            "id": generate_uuid7(),
            "name": "recruiter",
            "description": "Talent acquisition specialist",
            "is_system": True,
        },
        {
            "id": generate_uuid7(),
            "name": "hiring_manager",
            "description": "Department lead & interviewer",
            "is_system": True,
        },
        {
            "id": generate_uuid7(),
            "name": "org_admin",
            "description": "Organization administrator",
            "is_system": True,
        },
        {
            "id": generate_uuid7(),
            "name": "platform_super_admin",
            "description": "Platform SaaS operator",
            "is_system": True,
        },
    ]

    roles_table = sa.table(
        "roles",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(roles_table, roles_data)

    # Core capability permissions
    perms_data = [
        {
            "id": generate_uuid7(),
            "code": "candidate:profile:manage",
            "name": "Manage Candidate Profile",
            "module": "candidates",
        },
        {"id": generate_uuid7(), "code": "jobs:read", "name": "Read Jobs", "module": "jobs"},
        {"id": generate_uuid7(), "code": "jobs:create", "name": "Create Jobs", "module": "jobs"},
        {"id": generate_uuid7(), "code": "jobs:update", "name": "Update Jobs", "module": "jobs"},
        {"id": generate_uuid7(), "code": "jobs:delete", "name": "Delete Jobs", "module": "jobs"},
        {
            "id": generate_uuid7(),
            "code": "candidates:view_all",
            "name": "View All Candidates",
            "module": "candidates",
        },
        {
            "id": generate_uuid7(),
            "code": "candidates:view_assigned",
            "name": "View Assigned Candidates",
            "module": "candidates",
        },
        {
            "id": generate_uuid7(),
            "code": "screening:execute",
            "name": "Execute AI Screening",
            "module": "screening",
        },
        {
            "id": generate_uuid7(),
            "code": "screening:view",
            "name": "View Screening Results",
            "module": "screening",
        },
        {
            "id": generate_uuid7(),
            "code": "pipeline:transition",
            "name": "Transition Pipeline Stage",
            "module": "pipeline",
        },
        {
            "id": generate_uuid7(),
            "code": "interviews:schedule",
            "name": "Schedule Interviews",
            "module": "interviews",
        },
        {
            "id": generate_uuid7(),
            "code": "interviews:scorecard_submit",
            "name": "Submit Scorecards",
            "module": "interviews",
        },
        {
            "id": generate_uuid7(),
            "code": "org:manage",
            "name": "Manage Organization",
            "module": "organizations",
        },
        {
            "id": generate_uuid7(),
            "code": "org:members:manage",
            "name": "Manage Organization Members",
            "module": "organizations",
        },
    ]

    perms_table = sa.table(
        "permissions",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("module", sa.String),
    )
    op.bulk_insert(perms_table, perms_data)

    # 11. Grant runtime DML permissions to aihr_app_user
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aihr_app_user') THEN
                GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO aihr_app_user;
                GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO aihr_app_user;
                GRANT EXECUTE ON ALL ROUTINES IN SCHEMA public TO aihr_app_user;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    # Drop tables in reverse order
    op.execute(
        "DROP TRIGGER IF EXISTS trg_enforce_membership_role_tenant ON organization_memberships;"
    )
    op.execute("DROP FUNCTION IF EXISTS fn_enforce_membership_role_tenant();")
    op.drop_table("auth_revocation_outbox")
    op.drop_table("session_token_history")
    op.drop_table("user_sessions")
    op.execute("DROP POLICY IF EXISTS org_mem_tenant_restrict ON organization_memberships;")
    op.drop_table("organization_memberships")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
    op.drop_table("candidate_user_profiles")
    op.drop_table("users")
    op.drop_table("organizations")
