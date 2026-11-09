"""Comprehensive test suite for Secure Document Ingestion Pipeline conforming to Step 3.10.

Validates:
- Modular PDF extraction with pdfplumber (page-counts, text, timeouts, quality metrics).
- Scanned PDF detection and low-text thresholds.
- S3-compatible storage service (tenant-isolated paths, SHA-256 integrity, presigned URLs).
- OCR fallback provider architecture (NullOCRProvider, MockOCRProvider).
- Controlled lifecycle state machine (can_transition_document, invalid transition rejections).
- DocumentService orchestration (antivirus scanning, magic bytes, deduplication, tenant isolation).
- Celery processing task (process_document_task, failure states, orphaned recovery).
"""

from __future__ import annotations

import hashlib
import io
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.datastructures import UploadFile

from app.core.errors import EntityNotFoundException, ValidationException
from app.core.security.file_security import (
    FileSecurityException,
    validate_file_size,
    validate_pdf_content,
)
from app.modules.documents.extractor import (
    ExtractionException,
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
    MockOCRProvider,
    NullOCRProvider,
    get_ocr_provider,
    set_ocr_provider,
)
from app.modules.documents.service import DocumentService
from app.modules.documents.storage import (
    StorageIntegrityException,
    StorageService,
)
from app.modules.documents.tasks import (
    _async_process_document,
    parse_document,
    process_document_task,
    recover_orphaned_documents_task,
)

# -----------------------------------------------------------------------------
# Fixtures and Sample PDF Generators
# -----------------------------------------------------------------------------

SAMPLE_TEXT_PDF = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 124 >>
stream
BT
/F1 12 Tf
50 700 Td
(Jane Doe - Senior Python Cloud Architect with experience in FastAPI, Docker, and Kubernetes.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000052 00000 n
0000000109 00000 n
0000000227 00000 n
0000000419 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
519
%%EOF"""

SAMPLE_SCANNED_PDF = b"""%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >> endobj
4 0 obj << /Length 0 >> stream
endstream
endobj
xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000216 00000 n
trailer << /Size 5 /Root 1 0 R >>
startxref
267
%%EOF"""


# -----------------------------------------------------------------------------
# 1. PDF Extractor Service Tests
# -----------------------------------------------------------------------------


def test_pdf_extractor_valid_text_extraction() -> None:
    """Verify clean extraction of text, page count, and metrics from text-bearing PDF."""
    extractor = PDFExtractorService()
    result = extractor.extract_from_bytes(SAMPLE_TEXT_PDF)

    assert result.page_count == 1
    assert "Jane Doe" in result.raw_text
    assert "Senior Python Cloud Architect" in result.raw_text
    assert len(result.page_texts) == 1
    assert result.character_count > 0
    assert result.quality_score > 0.0
    assert result.requires_ocr is False
    assert result.is_scanned is False
    assert result.content_sha256 == hashlib.sha256(SAMPLE_TEXT_PDF).hexdigest()
    assert result.extraction_method == "pdfplumber_v1"


def test_pdf_extractor_scanned_pdf_detection() -> None:
    """Verify empty/image-only PDF flags requires_ocr=True and is_scanned=True."""
    extractor = PDFExtractorService()
    result = extractor.extract_from_bytes(SAMPLE_SCANNED_PDF)

    assert result.page_count == 1
    assert result.character_count == 0
    assert result.requires_ocr is True
    assert result.is_scanned is True
    assert result.quality_score == 0.0


def test_pdf_extractor_empty_bytes_raises_exception() -> None:
    """Verify extraction fails cleanly on 0-byte document."""
    extractor = PDFExtractorService()
    with pytest.raises(ExtractionException, match="empty document bytes"):
        extractor.extract_from_bytes(b"")


def test_pdf_extractor_page_limit_enforcement() -> None:
    """Verify PDF exceeding max allowable page count raises PDFResourceLimitException."""
    extractor = PDFExtractorService()
    # Pass max_pages=0 to trigger resource limit
    with pytest.raises(PDFResourceLimitException, match="exceeds the limit"):
        extractor.extract_from_bytes(SAMPLE_TEXT_PDF, max_pages=0)


# -----------------------------------------------------------------------------
# 2. Storage Service Tests
# -----------------------------------------------------------------------------


def test_storage_generate_tenant_storage_key() -> None:
    """Verify tenant isolation in generated object storage keys."""
    storage = StorageService()
    tenant_id = uuid4()
    key = storage.generate_tenant_storage_key(tenant_id, extension="pdf")

    assert key.startswith(f"tenants/{tenant_id}/documents/")
    assert key.endswith(".pdf")
    assert f"/{datetime.now(UTC).year}/" in key


def test_storage_upload_download_roundtrip_integrity() -> None:
    """Verify upload, download, and SHA-256 pre/post verification."""
    storage = StorageService()
    tenant_id = uuid4()
    key = storage.generate_tenant_storage_key(tenant_id)
    content = b"PDF dummy content payload"
    expected_hash = hashlib.sha256(content).hexdigest()

    # Upload
    uploaded_hash = storage.upload_document_bytes(
        file_bytes=content,
        storage_key=key,
        expected_sha256=expected_hash,
    )
    assert uploaded_hash == expected_hash

    # Download with verification
    downloaded = storage.download_document_bytes(key, expected_sha256=expected_hash)
    assert downloaded == content


def test_storage_integrity_mismatch_raises_exception() -> None:
    """Verify upload or download fails when SHA-256 does not match expected."""
    storage = StorageService()
    key = "tenants/test/doc.pdf"
    content = b"Authentic payload"
    tampered_hash = "0" * 64

    with pytest.raises(StorageIntegrityException, match="does not match expected"):
        storage.upload_document_bytes(
            file_bytes=content,
            storage_key=key,
            expected_sha256=tampered_hash,
        )


def test_storage_presigned_download_url_generation() -> None:
    """Verify presigned download URL generation includes expiry parameter."""
    storage = StorageService()
    key = "tenants/123/doc.pdf"
    url = storage.generate_presigned_download_url(key, expire_seconds=600)

    assert "expires=600" in url
    assert key in url


def test_storage_delete_object() -> None:
    """Verify deleting stored object removes it from store."""
    storage = StorageService()
    key = "tenants/test/delete_me.pdf"
    storage.upload_document_bytes(b"content", key)

    storage.delete_document_object(key)

    with pytest.raises(EntityNotFoundException):
        storage.download_document_bytes(key)


# -----------------------------------------------------------------------------
# 3. OCR Provider Architecture Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_null_ocr_provider_behavior() -> None:
    """Verify NullOCRProvider returns executed=False and reports unconfigured engine."""
    provider = NullOCRProvider()
    assert provider.provider_name == "null_ocr_unconfigured"

    result = await provider.extract_ocr_text(SAMPLE_SCANNED_PDF)
    assert result.executed is False
    assert result.raw_text == ""
    assert result.character_count == 0
    assert "not configured" in (result.error_message or "")


@pytest.mark.asyncio
async def test_mock_ocr_provider_behavior() -> None:
    """Verify MockOCRProvider simulates successful OCR extraction."""
    mock_text = "Extracted OCR candidate text"
    provider = MockOCRProvider(mock_text=mock_text, confidence=0.92)
    assert provider.provider_name == "mock_test_ocr"

    result = await provider.extract_ocr_text(SAMPLE_SCANNED_PDF)
    assert result.executed is True
    assert result.raw_text == mock_text
    assert result.confidence_score == 0.92
    assert result.character_count == len(mock_text)


def test_set_ocr_provider_switching() -> None:
    """Verify active OCR provider can be cleanly substituted."""
    default_provider = get_ocr_provider()
    try:
        mock = MockOCRProvider()
        set_ocr_provider(mock)
        assert get_ocr_provider() == mock
    finally:
        set_ocr_provider(default_provider)


# -----------------------------------------------------------------------------
# 4. Controlled Document Lifecycle State Machine Tests
# -----------------------------------------------------------------------------


def test_valid_document_lifecycle_transitions() -> None:
    """Verify all permitted state transitions in document lifecycle."""
    # UPLOADED transitions
    assert can_transition_document(DocumentStatus.UPLOADED, DocumentStatus.QUEUED)
    assert can_transition_document(DocumentStatus.UPLOADED, DocumentStatus.PROCESSING)
    assert can_transition_document(DocumentStatus.UPLOADED, DocumentStatus.FAILED)

    # QUEUED transitions
    assert can_transition_document(DocumentStatus.QUEUED, DocumentStatus.PROCESSING)
    assert can_transition_document(DocumentStatus.QUEUED, DocumentStatus.FAILED)

    # PROCESSING transitions
    assert can_transition_document(DocumentStatus.PROCESSING, DocumentStatus.COMPLETED)
    assert can_transition_document(DocumentStatus.PROCESSING, DocumentStatus.OCR_REQUIRED)
    assert can_transition_document(DocumentStatus.PROCESSING, DocumentStatus.FAILED)

    # OCR_REQUIRED transitions
    assert can_transition_document(DocumentStatus.OCR_REQUIRED, DocumentStatus.PROCESSING)
    assert can_transition_document(DocumentStatus.OCR_REQUIRED, DocumentStatus.COMPLETED)
    assert can_transition_document(DocumentStatus.OCR_REQUIRED, DocumentStatus.FAILED)

    # COMPLETED transitions
    assert can_transition_document(DocumentStatus.COMPLETED, DocumentStatus.DELETION_PENDING)

    # DELETION_PENDING transitions
    assert can_transition_document(DocumentStatus.DELETION_PENDING, DocumentStatus.DELETED)

    # Self-transitions (idempotent)
    assert can_transition_document(DocumentStatus.PROCESSING, DocumentStatus.PROCESSING)
    assert can_transition_document(DocumentStatus.COMPLETED, DocumentStatus.COMPLETED)


def test_invalid_document_lifecycle_transitions() -> None:
    """Verify illegal transitions are rejected by state machine."""
    # Cannot jump directly from UPLOADED to COMPLETED
    assert not can_transition_document(DocumentStatus.UPLOADED, DocumentStatus.COMPLETED)

    # Terminal DELETED state cannot transition to any active state
    assert not can_transition_document(DocumentStatus.DELETED, DocumentStatus.PROCESSING)
    assert not can_transition_document(DocumentStatus.DELETED, DocumentStatus.QUEUED)
    assert not can_transition_document(DocumentStatus.DELETED, DocumentStatus.COMPLETED)

    # COMPLETED cannot jump directly to PROCESSING
    assert not can_transition_document(DocumentStatus.COMPLETED, DocumentStatus.PROCESSING)


# -----------------------------------------------------------------------------
# 5. File Security & Antivirus Validation Tests
# -----------------------------------------------------------------------------


def test_validate_file_size_exceeded() -> None:
    """Verify oversized payload raises FileSecurityException."""
    max_size = 100
    oversized = b"A" * 101
    with pytest.raises(FileSecurityException, match="exceeds maximum allowed limit"):
        validate_file_size(oversized, max_size_bytes=max_size)


def test_validate_pdf_magic_bytes_failure() -> None:
    """Verify non-PDF file content is rejected."""
    bad_bytes = b"NOT_A_PDF_DOCUMENT_CONTENT"
    with pytest.raises(FileSecurityException, match="magic header"):
        validate_pdf_content(bad_bytes)


def test_validate_pdf_active_script_detection() -> None:
    """Verify PDFs containing embedded /JavaScript triggers are blocked."""
    malicious_pdf = SAMPLE_TEXT_PDF + b"\n/JavaScript << /JS (app.alert('PWNED')) >>"
    with pytest.raises(FileSecurityException, match="Malicious active content or script trigger"):
        validate_pdf_content(malicious_pdf)


# -----------------------------------------------------------------------------
# 6. Document Service & Deduplication Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_service_upload_new_and_deduplicate() -> None:
    """Verify document upload creates record, and identical second upload returns duplicate."""
    mock_db = AsyncMock()
    mock_storage = StorageService()
    service = DocumentService(storage=mock_storage)

    tenant_id = uuid4()
    user_id = uuid4()

    upload_file_1 = UploadFile(
        file=io.BytesIO(SAMPLE_TEXT_PDF),
        filename="resume.pdf",
        headers={"content-type": "application/pdf"},
    )

    # First call: no duplicate exists
    mock_exec_1 = MagicMock()
    mock_exec_1.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_exec_1

    with patch("app.modules.documents.tasks.process_document_task.delay") as mock_delay:
        resp1 = await service.upload_document(
            db=mock_db,
            tenant_id=tenant_id,
            user_id=user_id,
            file=upload_file_1,
        )

        assert resp1.is_duplicate is False
        assert resp1.tenant_id == tenant_id
        assert resp1.original_filename == "resume.pdf"
        assert resp1.content_sha256 == hashlib.sha256(SAMPLE_TEXT_PDF).hexdigest()
        assert mock_delay.called

    # Second call: duplicate exists
    existing_doc = Document(
        id=resp1.document_id,
        tenant_id=tenant_id,
        user_id=user_id,
        original_filename="resume.pdf",
        storage_key="tenants/key.pdf",
        file_size_bytes=len(SAMPLE_TEXT_PDF),
        mime_type="application/pdf",
        content_sha256=resp1.content_sha256,
        status=DocumentStatus.COMPLETED.value,
        created_at=datetime.now(UTC),
    )
    mock_exec_2 = MagicMock()
    mock_exec_2.scalar_one_or_none.return_value = existing_doc
    mock_db.execute.return_value = mock_exec_2

    upload_file_2 = UploadFile(
        file=io.BytesIO(SAMPLE_TEXT_PDF),
        filename="resume.pdf",
        headers={"content-type": "application/pdf"},
    )

    resp2 = await service.upload_document(
        db=mock_db,
        tenant_id=tenant_id,
        user_id=user_id,
        file=upload_file_2,
    )

    assert resp2.is_duplicate is True
    assert resp2.document_id == existing_doc.id


@pytest.mark.asyncio
async def test_document_service_rejects_non_pdf_extension() -> None:
    """Verify non-PDF file extension is rejected with ValidationException."""
    mock_db = AsyncMock()
    service = DocumentService()

    invalid_file = UploadFile(
        file=io.BytesIO(b"some content"),
        filename="resume.docx",
        headers={"content-type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"},
    )

    with pytest.raises(ValidationException, match="Only PDF document uploads are supported"):
        await service.upload_document(
            db=mock_db,
            tenant_id=uuid4(),
            user_id=uuid4(),
            file=invalid_file,
        )


# -----------------------------------------------------------------------------
# 7. Celery Task Execution Tests
# -----------------------------------------------------------------------------


def test_backward_compatible_parse_document_task() -> None:
    """Verify legacy parse_document task routes to document_processing and succeeds."""
    res = parse_document.apply(
        kwargs={
            "document_id": "doc-uuid-123",
            "tenant_id": "tenant-uuid-456",
            "s3_key": "tenants/tenant-uuid-456/doc.pdf",
        }
    )
    assert res.successful() is True
    assert res.result["status"] == "completed"
    assert res.result["document_id"] == "doc-uuid-123"
    assert res.result["tenant_id"] == "tenant-uuid-456"


@pytest.mark.asyncio
async def test_async_process_document_success() -> None:
    """Verify _async_process_document extracts text and transitions to COMPLETED."""
    tenant_id = uuid4()
    doc_id = uuid4()
    storage = StorageService()
    storage_key = storage.generate_tenant_storage_key(tenant_id)
    content_hash = hashlib.sha256(SAMPLE_TEXT_PDF).hexdigest()

    storage.upload_document_bytes(
        file_bytes=SAMPLE_TEXT_PDF,
        storage_key=storage_key,
        expected_sha256=content_hash,
    )

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="candidate.pdf",
        storage_key=storage_key,
        file_size_bytes=len(SAMPLE_TEXT_PDF),
        mime_type="application/pdf",
        content_sha256=content_hash,
        status=DocumentStatus.QUEUED.value,
    )

    mock_db = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db

        result = await _async_process_document(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            storage=storage,
        )

        assert result["status"] == DocumentStatus.COMPLETED.value
        assert result["document_id"] == str(doc_id)
        assert doc.status == DocumentStatus.COMPLETED.value
        assert mock_db.add.called  # DocumentExtraction added


@pytest.mark.asyncio
async def test_async_process_document_scanned_ocr_fallback() -> None:
    """Verify scanned document with NullOCRProvider transitions to OCR_REQUIRED."""
    tenant_id = uuid4()
    doc_id = uuid4()
    storage = StorageService()
    storage_key = storage.generate_tenant_storage_key(tenant_id)
    content_hash = hashlib.sha256(SAMPLE_SCANNED_PDF).hexdigest()

    storage.upload_document_bytes(
        file_bytes=SAMPLE_SCANNED_PDF,
        storage_key=storage_key,
        expected_sha256=content_hash,
    )

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="scanned.pdf",
        storage_key=storage_key,
        file_size_bytes=len(SAMPLE_SCANNED_PDF),
        mime_type="application/pdf",
        content_sha256=content_hash,
        status=DocumentStatus.QUEUED.value,
    )

    mock_db = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db

        result = await _async_process_document(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            storage=storage,
            ocr=NullOCRProvider(),
        )

        assert result["status"] == DocumentStatus.OCR_REQUIRED.value
        assert doc.status == DocumentStatus.OCR_REQUIRED.value
        assert doc.error_category == "OCR_REQUIRED"


@pytest.mark.asyncio
async def test_async_process_document_scanned_with_mock_ocr_succeeds() -> None:
    """Verify scanned document with configured OCR provider extracts text and completes."""
    tenant_id = uuid4()
    doc_id = uuid4()
    storage = StorageService()
    storage_key = storage.generate_tenant_storage_key(tenant_id)
    content_hash = hashlib.sha256(SAMPLE_SCANNED_PDF).hexdigest()

    storage.upload_document_bytes(
        file_bytes=SAMPLE_SCANNED_PDF,
        storage_key=storage_key,
        expected_sha256=content_hash,
    )

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="scanned.pdf",
        storage_key=storage_key,
        file_size_bytes=len(SAMPLE_SCANNED_PDF),
        mime_type="application/pdf",
        content_sha256=content_hash,
        status=DocumentStatus.QUEUED.value,
    )

    mock_db = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db

        result = await _async_process_document(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            storage=storage,
            ocr=MockOCRProvider(mock_text="Extracted text from scanned PDF"),
        )

        assert result["status"] == DocumentStatus.COMPLETED.value
        assert doc.status == DocumentStatus.COMPLETED.value
        assert result.get("ocr_applied") is True


# -----------------------------------------------------------------------------
# 8. Service Read, Extraction, Presigned URL, and Delete Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_document_service_get_status() -> None:
    """Verify DocumentService.get_document_status handles found and not-found records."""
    service = DocumentService()
    mock_db = AsyncMock()
    tenant_id = uuid4()
    doc_id = uuid4()

    # Not found
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_exec
    with pytest.raises(EntityNotFoundException):
        await service.get_document_status(mock_db, tenant_id, doc_id)

    # Found
    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="test.pdf",
        storage_key="key.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.COMPLETED.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    mock_exec.scalar_one_or_none.return_value = doc
    res = await service.get_document_status(mock_db, tenant_id, doc_id)
    assert res.document_id == doc_id
    assert res.status == DocumentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_document_service_get_extraction() -> None:
    """Verify DocumentService.get_document_extraction handles available, pending, and not-found."""
    service = DocumentService()
    tenant_id = uuid4()
    doc_id = uuid4()

    ext = DocumentExtraction(
        id=uuid4(),
        document_id=doc_id,
        tenant_id=tenant_id,
        page_count=2,
        character_count=500,
        extraction_method="pdfplumber_v1",
        extraction_version="1.0.0",
        raw_text="Extracted contents",
        page_texts=["Page 1", "Page 2"],
        quality_score=0.99,
        warnings=[],
        extracted_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="pending.pdf",
        storage_key="key.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.PROCESSING.value,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    current_extraction = ext
    current_doc = doc

    async def mock_execute(query, *args, **kwargs):
        q_str = str(query)
        res = MagicMock()
        if "document_extractions" in q_str:
            res.scalar_one_or_none.return_value = current_extraction
        elif "documents" in q_str:
            res.scalar_one_or_none.return_value = current_doc
        else:
            res.scalar_one_or_none.return_value = None
        return res

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=mock_execute)

    # 1. Extraction found
    res = await service.get_document_extraction(mock_db, tenant_id, doc_id)
    assert res.document_id == doc_id
    assert res.raw_text == "Extracted contents"
    assert res.page_count == 2

    # 2. Extraction not found, document pending
    current_extraction = None
    with pytest.raises(EntityNotFoundException, match="not yet available"):
        await service.get_document_extraction(mock_db, tenant_id, doc_id)

    # 3. Document completely absent
    current_doc = None
    with pytest.raises(EntityNotFoundException, match="was not found"):
        await service.get_document_extraction(mock_db, tenant_id, doc_id)



@pytest.mark.asyncio
async def test_document_service_get_presigned_download_url() -> None:
    """Verify DocumentService.get_presigned_download_url delegates to storage."""
    mock_storage = StorageService()
    service = DocumentService(storage=mock_storage)
    mock_db = AsyncMock()
    tenant_id = uuid4()
    doc_id = uuid4()

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="download.pdf",
        storage_key="tenants/download.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.COMPLETED.value,
    )
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    res = await service.get_presigned_download_url(mock_db, tenant_id, doc_id, expire_seconds=300)
    assert res.document_id == doc_id
    assert "expires=300" in res.download_url

    # Deleted document rejected
    doc.status = DocumentStatus.DELETED.value
    with pytest.raises(EntityNotFoundException):
        await service.get_presigned_download_url(mock_db, tenant_id, doc_id)


@pytest.mark.asyncio
async def test_document_service_delete_document() -> None:
    """Verify DocumentService.delete_document transitions to DELETED and deletes S3 object."""
    mock_storage = StorageService()
    service = DocumentService(storage=mock_storage)
    mock_db = AsyncMock()
    tenant_id = uuid4()
    doc_id = uuid4()

    storage_key = mock_storage.generate_tenant_storage_key(tenant_id)
    mock_storage.upload_document_bytes(b"content", storage_key)

    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="delete.pdf",
        storage_key=storage_key,
        file_size_bytes=7,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.COMPLETED.value,
    )
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    del_res = await service.delete_document(mock_db, tenant_id, doc_id)
    assert del_res.status == DocumentStatus.DELETED.value
    assert mock_db.delete.called

    # Second delete returns already deleted
    doc.status = DocumentStatus.DELETED.value
    del_res2 = await service.delete_document(mock_db, tenant_id, doc_id)
    assert "already been deleted" in del_res2.message


# -----------------------------------------------------------------------------
# 9. Celery Task Error Handling and Orphan Recovery Tests
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_process_document_doc_not_found_raises() -> None:
    """Verify task raises PermanentTaskError when document does not exist in DB."""
    from app.core.tasks.base import PermanentTaskError

    mock_db = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_exec

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db
        with pytest.raises(PermanentTaskError, match="not found"):
            await _async_process_document(str(uuid4()), str(uuid4()))


@pytest.mark.asyncio
async def test_async_process_document_already_completed() -> None:
    """Verify task returns early when document is already COMPLETED."""
    doc_id = uuid4()
    tenant_id = uuid4()
    doc = Document(
        id=doc_id,
        tenant_id=tenant_id,
        user_id=uuid4(),
        original_filename="done.pdf",
        storage_key="key.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.COMPLETED.value,
    )
    mock_db = AsyncMock()
    mock_exec = MagicMock()
    mock_exec.scalar_one_or_none.return_value = doc
    mock_db.execute.return_value = mock_exec

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db
        res = await _async_process_document(str(doc_id), str(tenant_id))
        assert res["status"] == DocumentStatus.COMPLETED.value


def test_recover_orphaned_documents_task_execution() -> None:
    """Verify recover_orphaned_documents_task finds and recovers orphaned PROCESSING documents."""
    orphaned_doc = Document(
        id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        original_filename="orphaned.pdf",
        storage_key="key.pdf",
        file_size_bytes=100,
        mime_type="application/pdf",
        content_sha256="hash",
        status=DocumentStatus.PROCESSING.value,
        updated_at=datetime.now(UTC) - timedelta(minutes=30),
    )

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [orphaned_doc]
    mock_db.execute.return_value = mock_result

    with patch("app.modules.documents.tasks.get_session_factory") as mock_factory:
        mock_factory.return_value.return_value.__aenter__.return_value = mock_db
        res = recover_orphaned_documents_task.apply(kwargs={"threshold_minutes": 15})

        assert res.successful() is True
        assert res.result["recovered_count"] == 1
        assert orphaned_doc.status == DocumentStatus.QUEUED.value

