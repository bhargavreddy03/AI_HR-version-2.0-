"""SQLAlchemy 2.x domain models for secure document ingestion conforming to Step 3.10.

Includes lifecycle status state machine, tenant-scoped storage metadata, and extraction results.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.base import Base, TenantScopedMixin, TimestampMixin, generate_uuid7, utc_now


class DocumentStatus(str, enum.Enum):
    """Controlled lifecycle states for document ingestion and text extraction."""

    UPLOADED = "UPLOADED"
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    OCR_REQUIRED = "OCR_REQUIRED"
    FAILED = "FAILED"
    DELETION_PENDING = "DELETION_PENDING"
    DELETED = "DELETED"


# Permitted state transition map guaranteeing concurrency-safe lifecycle
VALID_DOCUMENT_TRANSITIONS: dict[DocumentStatus, set[DocumentStatus]] = {
    DocumentStatus.UPLOADED: {
        DocumentStatus.QUEUED,
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    },
    DocumentStatus.QUEUED: {
        DocumentStatus.PROCESSING,
        DocumentStatus.FAILED,
    },
    DocumentStatus.PROCESSING: {
        DocumentStatus.COMPLETED,
        DocumentStatus.OCR_REQUIRED,
        DocumentStatus.FAILED,
    },
    DocumentStatus.OCR_REQUIRED: {
        DocumentStatus.PROCESSING,
        DocumentStatus.COMPLETED,
        DocumentStatus.FAILED,
    },
    DocumentStatus.COMPLETED: {
        DocumentStatus.DELETION_PENDING,
    },
    DocumentStatus.FAILED: {
        DocumentStatus.QUEUED,
        DocumentStatus.PROCESSING,
        DocumentStatus.DELETION_PENDING,
    },
    DocumentStatus.DELETION_PENDING: {
        DocumentStatus.DELETED,
        DocumentStatus.FAILED,
    },
    DocumentStatus.DELETED: set(),  # Terminal state
}


def can_transition_document(current: str | DocumentStatus, target: str | DocumentStatus) -> bool:
    """Validate whether requested lifecycle transition is permitted."""
    curr_enum = DocumentStatus(current) if isinstance(current, str) else current
    target_enum = DocumentStatus(target) if isinstance(target, str) else target

    if curr_enum == target_enum:
        return True
    return target_enum in VALID_DOCUMENT_TRANSITIONS.get(curr_enum, set())


class Document(Base, TenantScopedMixin, TimestampMixin):
    """Document metadata entity tracking stored files, tenant ownership, and lifecycle status."""

    __tablename__ = "documents"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    storage_key: Mapped[str] = mapped_column(
        String(512),
        nullable=False,
        unique=True,
        index=True,
    )
    file_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        default="application/pdf",
    )
    content_sha256: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
    )
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default=DocumentStatus.UPLOADED.value,
        index=True,
    )
    error_category: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )
    deletion_scheduled_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=True,
    )

    # Cascading relation to extraction records
    extractions: Mapped[list[DocumentExtraction]] = relationship(
        "DocumentExtraction",
        back_populates="document",
        cascade="all, delete-orphan",
        order_by="desc(DocumentExtraction.extracted_at)",
    )


class DocumentExtraction(Base, TenantScopedMixin, TimestampMixin):
    """Structured text extraction results derived from a processed document."""

    __tablename__ = "document_extractions"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        index=True,
    )
    document_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    page_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    character_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
    )
    extraction_method: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pdfplumber_v1",
    )
    extraction_version: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="1.0.0",
    )
    raw_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="",
    )
    page_texts: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    quality_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
    )
    warnings: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
    )
    extracted_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        default=utc_now,
    )

    document: Mapped[Document] = relationship(
        "Document",
        back_populates="extractions",
    )
