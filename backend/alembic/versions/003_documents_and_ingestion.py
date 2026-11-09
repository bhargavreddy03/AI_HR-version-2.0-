"""Document ingestion foundation and RLS security policies (Step 3.10).

Revision ID: 003_documents_ingestion
Revises: 002_db_foundation_pgvector
Create Date: 2026-11-09 16:30:00.000000
"""

import os
import re
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_documents_ingestion"
down_revision: str | None = "002_db_foundation_pgvector"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _get_app_role() -> str:
    """Return the configured runtime application role identifier safely."""
    role: str | None = None
    try:
        from app.core.config import get_settings

        settings = get_settings()
        role = getattr(settings, "DB_APP_ROLE", "ai_hr_app_user")
    except Exception:
        role = os.environ.get("DB_APP_ROLE", "ai_hr_app_user")

    if not role or not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", role):
        role = "ai_hr_app_user"

    return role


def upgrade() -> None:
    """Create documents and document_extractions tables with strict PostgreSQL RLS policies."""
    app_role = _get_app_role()

    # 1. Documents Table
    op.create_table(
        "documents",
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
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("file_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False, server_default="application/pdf"),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(50), nullable=False, server_default="UPLOADED"),
        sa.Column("error_category", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("deletion_scheduled_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index("ix_documents_tenant_id", "documents", ["tenant_id"])
    op.create_index("ix_documents_user_id", "documents", ["user_id"])
    op.create_index("ix_documents_content_sha256", "documents", ["content_sha256"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_index("ix_documents_tenant_sha256", "documents", ["tenant_id", "content_sha256"])

    # RLS on documents
    op.execute("ALTER TABLE documents ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE documents FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
                EXECUTE 'CREATE POLICY doc_app_user_perm ON documents
                         AS PERMISSIVE FOR ALL TO "{app_role}" USING (true) WITH CHECK (true);';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE POLICY doc_tenant_restrict ON documents
            AS RESTRICTIVE
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    """)

    # 2. Document Extractions Table
    op.create_table(
        "document_extractions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("page_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("character_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extraction_method", sa.String(50), nullable=False, server_default="pdfplumber_v1"),
        sa.Column("extraction_version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("raw_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("page_texts", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column("quality_score", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("warnings", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"),
        sa.Column(
            "extracted_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index("ix_document_extractions_document_id", "document_extractions", ["document_id"])
    op.create_index("ix_document_extractions_tenant_id", "document_extractions", ["tenant_id"])

    # RLS on document_extractions
    op.execute("ALTER TABLE document_extractions ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE document_extractions FORCE ROW LEVEL SECURITY;")
    op.execute(f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{app_role}') THEN
                EXECUTE 'CREATE POLICY doc_ext_app_user_perm ON document_extractions
                         AS PERMISSIVE FOR ALL TO "{app_role}" USING (true) WITH CHECK (true);';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE POLICY doc_ext_tenant_restrict ON document_extractions
            AS RESTRICTIVE
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    """)


def downgrade() -> None:
    """Drop document_extractions and documents tables and associated RLS policies."""
    op.execute("DROP POLICY IF EXISTS doc_ext_tenant_restrict ON document_extractions;")
    op.execute("DROP POLICY IF EXISTS doc_ext_app_user_perm ON document_extractions;")
    op.execute("DROP TABLE IF EXISTS document_extractions CASCADE;")

    op.execute("DROP POLICY IF EXISTS doc_tenant_restrict ON documents;")
    op.execute("DROP POLICY IF EXISTS doc_app_user_perm ON documents;")
    op.execute("DROP TABLE IF EXISTS documents CASCADE;")
