"""Pydantic v2 schemas and DTOs for Document Ingestion API conforming to Step 3.10."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload and initial queuing."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    tenant_id: UUID
    original_filename: str
    file_size_bytes: int
    content_sha256: str
    status: str
    created_at: datetime
    is_duplicate: bool = Field(
        default=False,
        description="True if an identical document was previously ingested for this tenant",
    )


class DocumentStatusResponse(BaseModel):
    """Detailed metadata and current processing lifecycle status for an ingested document."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    tenant_id: UUID
    user_id: UUID
    original_filename: str
    file_size_bytes: int
    mime_type: str
    content_sha256: str
    status: str
    error_category: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class DocumentExtractionResponse(BaseModel):
    """Structured text extraction results derived from a processed document."""

    model_config = ConfigDict(frozen=True)

    extraction_id: UUID
    document_id: UUID
    tenant_id: UUID
    page_count: int
    character_count: int
    extraction_method: str
    extraction_version: str
    raw_text: str
    page_texts: list[str]
    quality_score: float
    warnings: list[str]
    extracted_at: datetime


class DocumentDownloadUrlResponse(BaseModel):
    """Authorized, time-limited presigned S3 download URL for an ingested document."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    download_url: str
    expires_in_seconds: int


class DocumentDeleteResponse(BaseModel):
    """Confirmation of document deletion and storage object purging."""

    model_config = ConfigDict(frozen=True)

    document_id: UUID
    status: str
    message: str
