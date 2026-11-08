"""SQLAlchemy models for pgvector embeddings and model registry.

Conforms to Architecture Document 05 Section 2 and DATABASE_SECURITY_INVENTORY.md:
- Platform-Global Table 10: embedding_models
- Tenant-Scoped Table 22: candidate_document_embeddings
- Tenant-Scoped Table 23: job_embeddings
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, generate_uuid7, utc_now

APPROVED_MODELS: list[dict[str, object]] = [
    {
        "model_identifier": "text-embedding-3-small",
        "provider": "openai",
        "expected_dimensions": 1536,
        "is_active": True,
    },
    {
        "model_identifier": "amazon.titan-embed-text-v1",
        "provider": "aws_bedrock",
        "expected_dimensions": 1536,
        "is_active": True,
    },
    {
        "model_identifier": "cohere.embed-english-v3",
        "provider": "aws_bedrock",
        "expected_dimensions": 1024,
        "is_active": True,
    },
    {
        "model_identifier": "bge-base-en-v1.5",
        "provider": "huggingface",
        "expected_dimensions": 768,
        "is_active": True,
    },
]


class EmbeddingModel(Base):
    """Platform-Global Model Registry Table (Architecture Document 05 Section 2.A Table 10).

    Enforces uniqueness across (model_identifier, expected_dimensions) and restricts
    dimension configurations strictly to approved sizes (1536, 1024, 768).
    """

    __tablename__ = "embedding_models"
    __table_args__ = (
        CheckConstraint(
            "expected_dimensions IN (1536, 1024, 768)",
            name="chk_embedding_models_dimensions",
        ),
        UniqueConstraint(
            "model_identifier",
            "expected_dimensions",
            name="uq_embedding_models_dims",
        ),
    )

    model_identifier: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    expected_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class CandidateDocumentEmbedding(Base):
    """Tenant-Scoped Document Embeddings (Architecture Document 05 Section 2.B Table 22).

    Enforces model-to-dimension integrity via composite foreign key to embedding_models,
    exactly-one-vector-column check constraint, and tenant isolation via PostgreSQL RLS.
    """

    __tablename__ = "candidate_document_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_identifier", "vector_dimensions"],
            ["embedding_models.model_identifier", "embedding_models.expected_dimensions"],
            name="fk_cand_emb_model_dims",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "document_id",
            "model_identifier",
            "model_version",
            name="uq_cand_emb_version",
        ),
        CheckConstraint(
            "(vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)",
            name="chk_cand_emb_dimensions",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    model_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    vector_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_1536: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_1024: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    embedding_768: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )


class JobEmbedding(Base):
    """Tenant-Scoped Job Requisition Embeddings (Architecture Document 05 Section 2.C Table 23).

    Enforces model-to-dimension integrity via composite foreign key to embedding_models,
    exactly-one-vector-column check constraint, and tenant isolation via PostgreSQL RLS.
    """

    __tablename__ = "job_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["model_identifier", "vector_dimensions"],
            ["embedding_models.model_identifier", "embedding_models.expected_dimensions"],
            name="fk_job_emb_model_dims",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "job_id",
            "model_identifier",
            "model_version",
            name="uq_job_emb_version",
        ),
        CheckConstraint(
            "(vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR "
            "(vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)",
            name="chk_job_emb_dimensions",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    job_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    model_identifier: Mapped[str] = mapped_column(String(100), nullable=False)
    model_version: Mapped[str] = mapped_column(String(50), nullable=False)
    vector_dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding_1536: Mapped[list[float] | None] = mapped_column(Vector(1536), nullable=True)
    embedding_1024: Mapped[list[float] | None] = mapped_column(Vector(1024), nullable=True)
    embedding_768: Mapped[list[float] | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )
