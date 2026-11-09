"""Asynchronous background tasks for secure document processing pipeline."""

from __future__ import annotations

import asyncio
import concurrent.futures
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from sqlalchemy import select, text

from app.core.base import generate_uuid7, utc_now
from app.core.celery_app import celery_app
from app.core.database import get_session_factory
from app.core.tasks.base import BaseTask, PermanentTaskError, TransientTaskError
from app.core.tasks.idempotency import idempotent_task
from app.modules.documents.extractor import (
    ExtractionException,
    PDFEncryptedException,
    PDFExtractorService,
    PDFResourceLimitException,
)
from app.modules.documents.models import (
    Document,
    DocumentExtraction,
    DocumentStatus,
    can_transition_document,
)
from app.modules.documents.ocr import (
    BaseOCRProvider,
    get_ocr_provider,
)
from app.modules.documents.storage import (
    StorageException,
    StorageIntegrityException,
    StorageService,
    storage_service,
)

logger = logging.getLogger("app.modules.documents.tasks")


def _run_async(coro: Any) -> Any:
    """Safely execute an async coroutine within synchronous Celery task worker."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(asyncio.run, coro).result()
    return asyncio.run(coro)


async def _async_process_document(
    document_id: str,
    tenant_id: str,
    storage: StorageService | None = None,
    extractor: PDFExtractorService | None = None,
    ocr: BaseOCRProvider | None = None,
) -> dict[str, Any]:
    """Execute end-to-end document extraction asynchronously within database session."""
    active_storage = storage or storage_service
    active_extractor = extractor or PDFExtractorService()
    active_ocr = ocr or get_ocr_provider()

    doc_uuid = UUID(document_id)
    tenant_uuid = UUID(tenant_id)

    session_factory = get_session_factory()
    async with session_factory() as db:
        # Enforce transaction-local tenant context for RLS
        await db.execute(
            text("SELECT set_config('app.current_tenant_id', :tid, true)"),
            {"tid": str(tenant_uuid)},
        )

        result = await db.execute(
            select(Document).where(
                Document.id == doc_uuid,
                Document.tenant_id == tenant_uuid,
            )
        )
        doc = result.scalar_one_or_none()
        if not doc:
            logger.error("Document not found: id=%s, tenant_id=%s", document_id, tenant_id)
            raise PermanentTaskError(f"Document {document_id} not found")

        if doc.status in (DocumentStatus.COMPLETED.value, DocumentStatus.DELETED.value):
            logger.info("Document %s already terminal: status=%s", document_id, doc.status)
            return {"status": doc.status, "document_id": document_id}

        if can_transition_document(doc.status, DocumentStatus.PROCESSING):
            doc.status = DocumentStatus.PROCESSING.value
            await db.commit()
            await db.refresh(doc)
        elif doc.status != DocumentStatus.PROCESSING.value:
            logger.warning(
                "Document %s invalid transition from %s to PROCESSING",
                document_id,
                doc.status,
            )
            return {"status": doc.status, "document_id": document_id}

        # Retrieve binary payload from object storage with integrity verification
        try:
            content_bytes = active_storage.download_document_bytes(
                storage_key=doc.storage_key,
                expected_sha256=doc.content_sha256,
            )
        except StorageIntegrityException as exc:
            logger.error("Integrity check failed on storage_key=%s: %s", doc.storage_key, exc)
            doc.status = DocumentStatus.FAILED.value
            doc.error_category = "INTEGRITY_MISMATCH"
            doc.error_message = str(exc)
            await db.commit()
            raise PermanentTaskError(str(exc)) from exc
        except StorageException as exc:
            logger.warning("Transient storage error on storage_key=%s: %s", doc.storage_key, exc)
            raise TransientTaskError(f"Storage download failure: {exc}") from exc
        except Exception as exc:
            logger.error("Permanent storage failure on storage_key=%s: %s", doc.storage_key, exc)
            doc.status = DocumentStatus.FAILED.value
            doc.error_category = "STORAGE_ERROR"
            doc.error_message = f"Storage download failure: {exc}"
            await db.commit()
            raise PermanentTaskError(f"Storage download failure: {exc}") from exc

        # PDF extraction
        try:
            extraction_res = active_extractor.extract_from_bytes(content_bytes)
        except (PDFEncryptedException, PDFResourceLimitException) as exc:
            logger.error("Permanent extraction failure for doc=%s: %s", document_id, exc)
            doc.status = DocumentStatus.FAILED.value
            doc.error_category = exc.code if hasattr(exc, "code") else "EXTRACTION_FAILED"
            doc.error_message = str(exc)
            await db.commit()
            return {"status": "failed", "document_id": document_id, "error": str(exc)}
        except ExtractionException as exc:
            logger.error("Extractor error for doc=%s: %s", document_id, exc)
            doc.status = DocumentStatus.FAILED.value
            doc.error_category = "EXTRACTION_FAILED"
            doc.error_message = str(exc)
            await db.commit()
            return {"status": "failed", "document_id": document_id, "error": str(exc)}
        except Exception as exc:
            logger.warning("Transient extraction error for doc=%s: %s", document_id, exc)
            raise TransientTaskError(f"Extraction failed: {exc}") from exc

        # Check for scanned or low-text PDF needing OCR fallback
        if extraction_res.requires_ocr or extraction_res.is_scanned:
            logger.info("Scanned document detected for doc=%s; delegating to OCR", document_id)
            ocr_output = await active_ocr.extract_ocr_text(content_bytes)

            if not ocr_output.executed:
                doc.status = DocumentStatus.OCR_REQUIRED.value
                doc.error_category = "OCR_REQUIRED"
                doc.error_message = ocr_output.error_message or "Scanned document requires external OCR"
                now = utc_now()
                extraction = DocumentExtraction(
                    id=generate_uuid7(),
                    document_id=doc.id,
                    tenant_id=doc.tenant_id,
                    page_count=extraction_res.page_count,
                    character_count=0,
                    extraction_method=active_ocr.provider_name,
                    extraction_version="1.0.0",
                    raw_text="",
                    page_texts=[],
                    quality_score=0.0,
                    warnings=extraction_res.warnings + ["Scanned document requires external OCR"],
                    extracted_at=ocr_output.extracted_at,
                    created_at=now,
                    updated_at=now,
                )
                db.add(extraction)
                await db.commit()
                return {
                    "status": DocumentStatus.OCR_REQUIRED.value,
                    "document_id": document_id,
                    "ocr_provider": active_ocr.provider_name,
                }
            else:
                doc.status = DocumentStatus.COMPLETED.value
                doc.error_category = None
                doc.error_message = None
                now = utc_now()
                extraction = DocumentExtraction(
                    id=generate_uuid7(),
                    document_id=doc.id,
                    tenant_id=doc.tenant_id,
                    page_count=len(ocr_output.page_texts) or extraction_res.page_count,
                    character_count=ocr_output.character_count,
                    extraction_method=f"ocr_{active_ocr.provider_name}",
                    extraction_version="1.0.0",
                    raw_text=ocr_output.raw_text,
                    page_texts=ocr_output.page_texts,
                    quality_score=ocr_output.confidence_score,
                    warnings=extraction_res.warnings,
                    extracted_at=ocr_output.extracted_at,
                    created_at=now,
                    updated_at=now,
                )
                db.add(extraction)
                await db.commit()
                return {
                    "status": DocumentStatus.COMPLETED.value,
                    "document_id": document_id,
                    "ocr_applied": True,
                    "character_count": ocr_output.character_count,
                }

        # Standard extraction success
        doc.status = DocumentStatus.COMPLETED.value
        doc.error_category = None
        doc.error_message = None
        now = utc_now()
        extraction = DocumentExtraction(
            id=generate_uuid7(),
            document_id=doc.id,
            tenant_id=doc.tenant_id,
            page_count=extraction_res.page_count,
            character_count=extraction_res.character_count,
            extraction_method=extraction_res.extraction_method,
            extraction_version=extraction_res.extraction_version,
            raw_text=extraction_res.raw_text,
            page_texts=extraction_res.page_texts,
            quality_score=extraction_res.quality_score,
            warnings=extraction_res.warnings,
            extracted_at=extraction_res.extraction_timestamp,
            created_at=now,
            updated_at=now,
        )
        db.add(extraction)
        await db.commit()

        return {
            "status": DocumentStatus.COMPLETED.value,
            "document_id": document_id,
            "page_count": extraction_res.page_count,
            "character_count": extraction_res.character_count,
        }


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.modules.documents.tasks.process_document_task",
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
@idempotent_task(key_param="idempotency_key", lock_ttl=360, result_ttl=3600)
def process_document_task(
    self: Any,
    document_id: str,
    tenant_id: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Execute end-to-end asynchronous document processing pipeline."""
    logger.info(
        "Executing process_document_task: id=%s, tenant_id=%s, task_id=%s",
        document_id,
        tenant_id,
        self.request.id,
    )
    return _run_async(_async_process_document(document_id=document_id, tenant_id=tenant_id))


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.modules.documents.tasks.recover_orphaned_documents",
)
def recover_orphaned_documents_task(
    self: Any,
    threshold_minutes: int = 15,
) -> dict[str, Any]:
    """Recover documents stranded in PROCESSING due to worker crash."""
    async def _recover() -> int:
        cutoff = datetime.now(UTC) - timedelta(minutes=threshold_minutes)
        session_factory = get_session_factory()
        async with session_factory() as db:
            result = await db.execute(
                select(Document).where(
                    Document.status == DocumentStatus.PROCESSING.value,
                    Document.updated_at < cutoff,
                )
            )
            orphaned = result.scalars().all()
            for doc in orphaned:
                doc.status = DocumentStatus.QUEUED.value
                doc.error_message = (
                    f"Recovered from orphaned PROCESSING state after {threshold_minutes}m timeout"
                )
            await db.commit()
            return len(orphaned)

    count = _run_async(_recover())
    logger.info("Recovered %d orphaned documents", count)
    return {"recovered_count": count}


@celery_app.task(
    bind=True,
    base=BaseTask,
    name="app.modules.documents.tasks.parse_document",
    autoretry_for=(TransientTaskError,),
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def parse_document(
    self: Any,
    document_id: str,
    tenant_id: str,
    s3_key: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible document parsing task routed to document_processing queue."""
    logger.info(
        "Parsing document: id=%s, tenant_id=%s, s3_key=%s",
        document_id,
        tenant_id,
        s3_key,
    )
    return {
        "status": "completed",
        "document_id": document_id,
        "tenant_id": tenant_id,
        "queue": getattr(self.request, "delivery_info", {}).get(
            "routing_key", "document_processing"
        ),
        "task_id": self.request.id,
    }
