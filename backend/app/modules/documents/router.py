"""FastAPI API endpoints for secure multi-tenant document ingestion and extraction conforming to Step 3.10."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AuthorizationException
from app.core.security import SecurityContext
from app.modules.auth.dependencies import require_permission
from app.modules.documents.schemas import (
    DocumentDeleteResponse,
    DocumentDownloadUrlResponse,
    DocumentExtractionResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.modules.documents.service import document_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/documents", tags=["Documents & Secure Ingestion"])

# Explicit module-level permission dependencies enabling testing and override ergonomics
require_documents_upload = require_permission("documents:upload")
require_documents_read = require_permission("documents:read")
require_documents_delete = require_permission("documents:delete")


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document for processing",
)
async def upload_document(
    response: Response,
    file: UploadFile = File(..., description="PDF document binary payload"),
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_documents_upload),
) -> DocumentUploadResponse:
    """Securely upload a PDF document with antivirus validation, deduplication, and async task dispatch."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context is required for document uploads",
            error_code="TENANT_CONTEXT_REQUIRED",
        )

    res = await document_service.upload_document(
        db=db,
        tenant_id=security_context.tenant_id,
        user_id=security_context.user_id,
        file=file,
    )

    if res.is_duplicate:
        response.status_code = status.HTTP_200_OK

    return res


@router.get(
    "/{id}",
    response_model=DocumentStatusResponse,
    summary="Retrieve document metadata and lifecycle status",
)
async def get_document_status(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_documents_read),
) -> DocumentStatusResponse:
    """Retrieve current lifecycle status and metadata for a tenant's document."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context is required for document retrieval",
            error_code="TENANT_CONTEXT_REQUIRED",
        )

    return await document_service.get_document_status(
        db=db,
        tenant_id=security_context.tenant_id,
        document_id=id,
    )


@router.get(
    "/{id}/extraction",
    response_model=DocumentExtractionResponse,
    summary="Retrieve extracted text and quality metrics",
)
async def get_document_extraction(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_documents_read),
) -> DocumentExtractionResponse:
    """Retrieve structured text extraction results for a processed document."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context is required for extraction retrieval",
            error_code="TENANT_CONTEXT_REQUIRED",
        )

    return await document_service.get_document_extraction(
        db=db,
        tenant_id=security_context.tenant_id,
        document_id=id,
    )


@router.get(
    "/{id}/download-url",
    response_model=DocumentDownloadUrlResponse,
    summary="Generate a time-limited presigned download URL",
)
async def get_download_url(
    id: UUID,
    expires_in: int = Query(
        default=900,
        ge=60,
        le=86400,
        description="Presigned URL validity duration in seconds",
    ),
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_documents_read),
) -> DocumentDownloadUrlResponse:
    """Generate an authorized temporary download URL for the document payload."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context is required for document download",
            error_code="TENANT_CONTEXT_REQUIRED",
        )

    return await document_service.get_presigned_download_url(
        db=db,
        tenant_id=security_context.tenant_id,
        document_id=id,
        expire_seconds=expires_in,
    )


@router.delete(
    "/{id}",
    response_model=DocumentDeleteResponse,
    summary="Purge a document, extractions, and storage object",
)
async def delete_document(
    id: UUID,
    db: AsyncSession = Depends(get_db),
    security_context: SecurityContext = Depends(require_documents_delete),
) -> DocumentDeleteResponse:
    """Safely purge document database records and underlying S3 storage objects."""
    if not security_context.tenant_id:
        raise AuthorizationException(
            "Tenant context is required for document deletion",
            error_code="TENANT_CONTEXT_REQUIRED",
        )

    return await document_service.delete_document(
        db=db,
        tenant_id=security_context.tenant_id,
        document_id=id,
    )
