"""Document service orchestrating secure upload, deduplication, lifecycle transitions, and S3 storage.

Conforms strictly to Step 3.10 architecture.
"""

from __future__ import annotations

import hashlib
import logging
from uuid import UUID

from fastapi import UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.base import generate_uuid7, utc_now
from app.core.errors import (
    EntityNotFoundException as NotFoundException,
)
from app.core.errors import (
    ValidationException,
)
from app.core.security.context import set_tenant_context
from app.core.security.file_security import (
    MAX_FILE_SIZE_BYTES,
    FileSecurityException,
    get_malware_scanner,
    sanitize_filename,
    validate_file_size,
    validate_pdf_content,
)
from app.modules.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
)
from app.modules.documents.schemas import (
    DocumentDeleteResponse,
    DocumentDownloadUrlResponse,
    DocumentExtractionResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.modules.documents.storage import StorageService, storage_service

logger = logging.getLogger(__name__)


class DocumentService:
    """Enterprise domain service for secure multi-tenant document ingestion."""

    def __init__(self, storage: StorageService | None = None) -> None:
        self._storage = storage or storage_service

    async def upload_document(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        user_id: UUID,
        file: UploadFile,
    ) -> DocumentUploadResponse:
        """Process incoming document upload, enforce security bounds, deduplicate, and persist."""
        # 1. Enforce PostgreSQL RLS tenant context
        await set_tenant_context(db, tenant_id)

        # 2. Sanitize and validate client-supplied filename
        raw_filename = file.filename or "uploaded_document.pdf"
        clean_filename = sanitize_filename(raw_filename)

        if not clean_filename.lower().endswith(".pdf"):
            raise ValidationException("Only PDF document uploads are supported (.pdf)", code="ERR_UNSUPPORTED_DOCUMENT_TYPE")

        # 3. Read uploaded payload into memory
        file_bytes = await file.read()
        file_size = len(file_bytes)

        # 4. Enforce strict file size limits
        validate_file_size(file_bytes, max_size_bytes=MAX_FILE_SIZE_BYTES)

        # 5. Enforce magic bytes and PDF structure validation
        validate_pdf_content(file_bytes)

        # 6. Execute malware scanner inspection
        scanner = get_malware_scanner()
        scan_result = await scanner.scan(file_bytes, clean_filename)
        if not scan_result.is_clean:
            threat = scan_result.threat_name or "Malicious payload detected"
            logger.warning("Rejected malicious upload: filename=%s, threat=%s", clean_filename, threat)
            raise FileSecurityException(f"Document failed antivirus inspection: {threat}")

        # 7. Compute SHA-256 content digest
        content_sha256 = hashlib.sha256(file_bytes).hexdigest()

        # 8. Check for tenant-scoped deduplication
        existing_doc_stmt = (
            select(Document)
            .where(
                Document.tenant_id == tenant_id,
                Document.content_sha256 == content_sha256,
                Document.status.in_([
                    DocumentStatus.COMPLETED.value,
                    DocumentStatus.PROCESSING.value,
                    DocumentStatus.QUEUED.value,
                ]),
            )
            .limit(1)
        )
        existing_result = await db.execute(existing_doc_stmt)
        existing_doc = existing_result.scalar_one_or_none()

        if existing_doc:
            logger.info(
                "Duplicate document detected for tenant %s (sha256=%s). Returning existing doc %s",
                tenant_id,
                content_sha256,
                existing_doc.id,
            )
            return DocumentUploadResponse(
                document_id=existing_doc.id,
                tenant_id=existing_doc.tenant_id,
                original_filename=existing_doc.original_filename,
                file_size_bytes=existing_doc.file_size_bytes,
                content_sha256=existing_doc.content_sha256,
                status=existing_doc.status,
                created_at=existing_doc.created_at or utc_now(),
                is_duplicate=True,
            )

        # 9. Generate tenant-scoped storage key and upload to S3 object storage
        storage_key = self._storage.generate_tenant_storage_key(tenant_id, extension="pdf")
        self._storage.upload_document_bytes(
            file_bytes=file_bytes,
            storage_key=storage_key,
            mime_type=file.content_type or "application/pdf",
            expected_sha256=content_sha256,
        )

        # 10. Persist Document record in PostgreSQL
        now = utc_now()
        doc = Document(
            id=generate_uuid7(),
            tenant_id=tenant_id,
            user_id=user_id,
            original_filename=clean_filename,
            storage_key=storage_key,
            file_size_bytes=file_size,
            mime_type=file.content_type or "application/pdf",
            content_sha256=content_sha256,
            status=DocumentStatus.UPLOADED.value,
            created_at=now,
            updated_at=now,
        )
        db.add(doc)
        await db.commit()
        await db.refresh(doc)

        # 11. Enqueue asynchronous Celery processing task after commit
        try:
            from app.modules.documents.tasks import process_document_task

            process_document_task.delay(document_id=str(doc.id), tenant_id=str(tenant_id))

            # Concurrency-safe transition to QUEUED
            doc.status = DocumentStatus.QUEUED.value
            await db.commit()
            await db.refresh(doc)
        except Exception as exc:
            logger.error("Failed to enqueue Celery task for doc %s: %s", doc.id, exc)
            # Retain in UPLOADED state for worker recovery polling

        return DocumentUploadResponse(
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            original_filename=doc.original_filename,
            file_size_bytes=doc.file_size_bytes,
            content_sha256=doc.content_sha256,
            status=doc.status,
            created_at=doc.created_at,
            is_duplicate=False,
        )

    async def get_document_status(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        document_id: UUID,
    ) -> DocumentStatusResponse:
        """Retrieve authoritative metadata and current status for a tenant's document."""
        await set_tenant_context(db, tenant_id)

        stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document with ID {document_id} was not found")

        return DocumentStatusResponse(
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            user_id=doc.user_id,
            original_filename=doc.original_filename,
            file_size_bytes=doc.file_size_bytes,
            mime_type=doc.mime_type,
            content_sha256=doc.content_sha256,
            status=doc.status,
            error_category=doc.error_category,
            error_message=doc.error_message,
            created_at=doc.created_at,
            updated_at=doc.updated_at,
        )

    async def get_document_extraction(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        document_id: UUID,
    ) -> DocumentExtractionResponse:
        """Retrieve structured text extraction results for a completed document."""
        await set_tenant_context(db, tenant_id)

        stmt = (
            select(DocumentExtraction)
            .where(
                DocumentExtraction.document_id == document_id,
                DocumentExtraction.tenant_id == tenant_id,
            )
            .order_by(DocumentExtraction.extracted_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        extraction = result.scalar_one_or_none()

        if not extraction:
            # Check if document exists
            doc_stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
            doc_res = await db.execute(doc_stmt)
            doc = doc_res.scalar_one_or_none()
            if not doc:
                raise NotFoundException(f"Document with ID {document_id} was not found")
            raise NotFoundException(f"Extraction result for document {document_id} is not yet available (status: {doc.status})")

        return DocumentExtractionResponse(
            extraction_id=extraction.id,
            document_id=extraction.document_id,
            tenant_id=extraction.tenant_id,
            page_count=extraction.page_count,
            character_count=extraction.character_count,
            extraction_method=extraction.extraction_method,
            extraction_version=extraction.extraction_version,
            raw_text=extraction.raw_text,
            page_texts=list(extraction.page_texts or []),
            quality_score=extraction.quality_score,
            warnings=list(extraction.warnings or []),
            extracted_at=extraction.extracted_at,
        )

    async def get_presigned_download_url(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        document_id: UUID,
        expire_seconds: int = 900,
    ) -> DocumentDownloadUrlResponse:
        """Generate time-limited presigned URL for authorized secure document download."""
        await set_tenant_context(db, tenant_id)

        stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc or doc.status == DocumentStatus.DELETED.value:
            raise NotFoundException(f"Document with ID {document_id} was not found")

        download_url = self._storage.generate_presigned_download_url(
            storage_key=doc.storage_key,
            expire_seconds=expire_seconds,
        )

        return DocumentDownloadUrlResponse(
            document_id=doc.id,
            download_url=download_url,
            expires_in_seconds=expire_seconds,
        )

    async def delete_document(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        document_id: UUID,
    ) -> DocumentDeleteResponse:
        """Execute tenant-scoped document deletion and storage cleanup."""
        await set_tenant_context(db, tenant_id)

        stmt = select(Document).where(Document.id == document_id, Document.tenant_id == tenant_id)
        result = await db.execute(stmt)
        doc = result.scalar_one_or_none()

        if not doc:
            raise NotFoundException(f"Document with ID {document_id} was not found")

        if doc.status == DocumentStatus.DELETED.value:
            return DocumentDeleteResponse(
                document_id=doc.id,
                status=DocumentStatus.DELETED.value,
                message="Document has already been deleted",
            )

        # 1. Concurrency-safe transition to DELETION_PENDING
        doc.status = DocumentStatus.DELETION_PENDING.value
        doc.deletion_scheduled_at = utc_now()
        await db.commit()

        # 2. Delete storage object from S3
        self._storage.delete_document_object(doc.storage_key)

        # 3. Delete database records (cascade drops extractions)
        await db.delete(doc)
        await db.commit()

        logger.info("Deleted document %s and associated storage for tenant %s", document_id, tenant_id)
        return DocumentDeleteResponse(
            document_id=document_id,
            status=DocumentStatus.DELETED.value,
            message="Document and extracted content successfully purged",
        )


# Global singleton instance
document_service = DocumentService()
