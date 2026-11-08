"""Database foundation and pgvector integration (Step 3.4).

Revision ID: 002_db_foundation_pgvector
Revises: 001_auth_identity
Create Date: 2026-11-08 10:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002_db_foundation_pgvector"
down_revision: str | None = "001_auth_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # --------------------------------------------------------------------------
    # 1. Enable PostgreSQL pgvector Extension
    # --------------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # --------------------------------------------------------------------------
    # 2. Platform-Global Model Registry: embedding_models (Table 10)
    # --------------------------------------------------------------------------
    op.create_table(
        "embedding_models",
        sa.Column("model_identifier", sa.String(100), primary_key=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("expected_dimensions", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.CheckConstraint(
            "expected_dimensions IN (1536, 1024, 768)",
            name="chk_embedding_models_dimensions",
        ),
        sa.UniqueConstraint(
            "model_identifier",
            "expected_dimensions",
            name="uq_embedding_models_dims",
        ),
    )

    # Seed approved model registry records
    op.execute("""
        INSERT INTO embedding_models (model_identifier, provider, expected_dimensions, is_active) VALUES
        ('text-embedding-3-small', 'openai', 1536, true),
        ('amazon.titan-embed-text-v1', 'aws_bedrock', 1536, true),
        ('cohere.embed-english-v3', 'aws_bedrock', 1024, true),
        ('bge-base-en-v1.5', 'huggingface', 768, true)
        ON CONFLICT (model_identifier) DO NOTHING;
    """)

    # --------------------------------------------------------------------------
    # 3. Tenant-Scoped Document Embeddings: candidate_document_embeddings (Table 22)
    # --------------------------------------------------------------------------
    op.create_table(
        "candidate_document_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_identifier", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("vector_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_1536", Vector(1536), nullable=True),
        sa.Column("embedding_1024", Vector(1024), nullable=True),
        sa.Column("embedding_768", Vector(768), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["model_identifier", "vector_dimensions"],
            ["embedding_models.model_identifier", "embedding_models.expected_dimensions"],
            name="fk_cand_emb_model_dims",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "document_id",
            "model_identifier",
            "model_version",
            name="uq_cand_emb_version",
        ),
        sa.CheckConstraint(
            "(vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)",
            name="chk_cand_emb_dimensions",
        ),
    )
    op.create_index(
        "ix_candidate_document_embeddings_tenant_id",
        "candidate_document_embeddings",
        ["tenant_id"],
    )
    op.create_index(
        "ix_candidate_document_embeddings_document_id",
        "candidate_document_embeddings",
        ["document_id"],
    )

    # Partial HNSW Indexes on candidate_document_embeddings
    op.execute("""
        CREATE INDEX idx_cand_emb_1536 ON candidate_document_embeddings 
            USING hnsw (embedding_1536 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_1536 IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX idx_cand_emb_1024 ON candidate_document_embeddings 
            USING hnsw (embedding_1024 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_1024 IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX idx_cand_emb_768 ON candidate_document_embeddings 
            USING hnsw (embedding_768 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_768 IS NOT NULL;
    """)

    # Enable and Force Row Level Security on candidate_document_embeddings
    op.execute("ALTER TABLE candidate_document_embeddings ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE candidate_document_embeddings FORCE ROW LEVEL SECURITY;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aihr_app_user') THEN
                EXECUTE 'CREATE POLICY cand_emb_app_user_perm ON candidate_document_embeddings
                         AS PERMISSIVE FOR ALL TO aihr_app_user USING (true) WITH CHECK (true);';
            ELSE
                EXECUTE 'CREATE POLICY cand_emb_app_user_perm ON candidate_document_embeddings
                         AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE POLICY cand_emb_tenant_restrict ON candidate_document_embeddings
            AS RESTRICTIVE
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    """)

    # --------------------------------------------------------------------------
    # 4. Tenant-Scoped Job Embeddings: job_embeddings (Table 23)
    # --------------------------------------------------------------------------
    op.create_table(
        "job_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("model_identifier", sa.String(100), nullable=False),
        sa.Column("model_version", sa.String(50), nullable=False),
        sa.Column("vector_dimensions", sa.Integer(), nullable=False),
        sa.Column("embedding_1536", Vector(1536), nullable=True),
        sa.Column("embedding_1024", Vector(1024), nullable=True),
        sa.Column("embedding_768", Vector(768), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.ForeignKeyConstraint(
            ["model_identifier", "vector_dimensions"],
            ["embedding_models.model_identifier", "embedding_models.expected_dimensions"],
            name="fk_job_emb_model_dims",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "job_id",
            "model_identifier",
            "model_version",
            name="uq_job_emb_version",
        ),
        sa.CheckConstraint(
            "(vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)",
            name="chk_job_emb_dimensions",
        ),
    )
    op.create_index(
        "ix_job_embeddings_tenant_id",
        "job_embeddings",
        ["tenant_id"],
    )
    op.create_index(
        "ix_job_embeddings_job_id",
        "job_embeddings",
        ["job_id"],
    )

    # Partial HNSW Indexes on job_embeddings
    op.execute("""
        CREATE INDEX idx_job_emb_1536 ON job_embeddings 
            USING hnsw (embedding_1536 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_1536 IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX idx_job_emb_1024 ON job_embeddings 
            USING hnsw (embedding_1024 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_1024 IS NOT NULL;
    """)
    op.execute("""
        CREATE INDEX idx_job_emb_768 ON job_embeddings 
            USING hnsw (embedding_768 vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            WHERE embedding_768 IS NOT NULL;
    """)

    # Enable and Force Row Level Security on job_embeddings
    op.execute("ALTER TABLE job_embeddings ENABLE ROW LEVEL SECURITY;")
    op.execute("ALTER TABLE job_embeddings FORCE ROW LEVEL SECURITY;")
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'aihr_app_user') THEN
                EXECUTE 'CREATE POLICY job_emb_app_user_perm ON job_embeddings
                         AS PERMISSIVE FOR ALL TO aihr_app_user USING (true) WITH CHECK (true);';
            ELSE
                EXECUTE 'CREATE POLICY job_emb_app_user_perm ON job_embeddings
                         AS PERMISSIVE FOR ALL TO PUBLIC USING (true) WITH CHECK (true);';
            END IF;
        END $$;
    """)
    op.execute("""
        CREATE POLICY job_emb_tenant_restrict ON job_embeddings
            AS RESTRICTIVE
            FOR ALL
            USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    """)


def downgrade() -> None:
    # 1. Drop job_embeddings policies, indexes, and table
    op.execute("DROP POLICY IF EXISTS job_emb_tenant_restrict ON job_embeddings;")
    op.execute("DROP POLICY IF EXISTS job_emb_app_user_perm ON job_embeddings;")
    op.drop_table("job_embeddings")

    # 2. Drop candidate_document_embeddings policies, indexes, and table
    op.execute("DROP POLICY IF EXISTS cand_emb_tenant_restrict ON candidate_document_embeddings;")
    op.execute("DROP POLICY IF EXISTS cand_emb_app_user_perm ON candidate_document_embeddings;")
    op.drop_table("candidate_document_embeddings")

    # 3. Drop embedding_models table
    op.drop_table("embedding_models")

    # 4. Safely drop vector extension if no other tables use it
    op.execute("DROP EXTENSION IF EXISTS vector CASCADE;")
