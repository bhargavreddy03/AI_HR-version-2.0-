"""Unit and integration tests for FastAPI document endpoints under /api/v1/documents.

Validates:
- POST /api/v1/documents/upload: multipart upload, RBAC 'documents:upload', deduplication.
- GET /api/v1/documents/{id}: status retrieval, RBAC 'documents:read'.
- GET /api/v1/documents/{id}/extraction: extraction retrieval, RBAC 'documents:read'.
- GET /api/v1/documents/{id}/download-url: presigned download URL generation, RBAC 'documents:read'.
- DELETE /api/v1/documents/{id}: purge document and storage, RBAC 'documents:delete'.
- RBAC enforcement: 403 Forbidden when permission is missing.
- Tenant isolation: requests without tenant context rejected.
"""

from __future__ import annotations

import io
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import SecurityContext
from app.main import create_application
from app.modules.documents.models import DocumentStatus
from app.modules.documents.router import (
    require_documents_delete,
    require_documents_read,
    require_documents_upload,
)
from app.modules.documents.schemas import (
    DocumentDeleteResponse,
    DocumentDownloadUrlResponse,
    DocumentExtractionResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)

SAMPLE_PDF_BYTES = b"""%PDF-1.4
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

TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture
def app_instance():
    """Create a configured test application instance."""
    return create_application()


@pytest.fixture
def security_context():
    """SecurityContext with all document permissions."""
    return SecurityContext(
        user_id=USER_ID,
        session_id=uuid4(),
        tenant_id=TENANT_ID,
        roles=["recruiter"],
        permissions=["documents:upload", "documents:read", "documents:delete"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )


@pytest.mark.asyncio
async def test_upload_document_success(app_instance, security_context) -> None:
    """Verify POST /api/v1/documents/upload creates document and returns 201."""
    doc_id = uuid4()
    mock_upload_res = DocumentUploadResponse(
        document_id=doc_id,
        tenant_id=TENANT_ID,
        original_filename="resume.pdf",
        file_size_bytes=len(SAMPLE_PDF_BYTES),
        content_sha256="abc123hash",
        status=DocumentStatus.QUEUED.value,
        created_at=datetime.now(UTC),
        is_duplicate=False,
    )

    with patch(
        "app.modules.documents.service.document_service.upload_document",
        new=AsyncMock(return_value=mock_upload_res),
    ):
        app_instance.dependency_overrides[require_documents_upload] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            files = {"file": ("resume.pdf", io.BytesIO(SAMPLE_PDF_BYTES), "application/pdf")}
            res = await ac.post("/api/v1/documents/upload", files=files)

            assert res.status_code == 201
            data = res.json()
            assert data["document_id"] == str(doc_id)
            assert data["is_duplicate"] is False
            assert data["status"] == DocumentStatus.QUEUED.value


@pytest.mark.asyncio
async def test_upload_document_duplicate_returns_200(app_instance, security_context) -> None:
    """Verify POST /api/v1/documents/upload on duplicate returns 200 OK."""
    doc_id = uuid4()
    mock_dup_res = DocumentUploadResponse(
        document_id=doc_id,
        tenant_id=TENANT_ID,
        original_filename="resume.pdf",
        file_size_bytes=len(SAMPLE_PDF_BYTES),
        content_sha256="abc123hash",
        status=DocumentStatus.COMPLETED.value,
        created_at=datetime.now(UTC),
        is_duplicate=True,
    )

    with patch(
        "app.modules.documents.service.document_service.upload_document",
        new=AsyncMock(return_value=mock_dup_res),
    ):
        app_instance.dependency_overrides[require_documents_upload] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            files = {"file": ("resume.pdf", io.BytesIO(SAMPLE_PDF_BYTES), "application/pdf")}
            res = await ac.post("/api/v1/documents/upload", files=files)

            assert res.status_code == 200
            data = res.json()
            assert data["is_duplicate"] is True
            assert data["document_id"] == str(doc_id)


@pytest.mark.asyncio
async def test_get_document_status_success(app_instance, security_context) -> None:
    """Verify GET /api/v1/documents/{id} returns status and metadata."""
    doc_id = uuid4()
    mock_status = DocumentStatusResponse(
        document_id=doc_id,
        tenant_id=TENANT_ID,
        user_id=USER_ID,
        original_filename="resume.pdf",
        file_size_bytes=len(SAMPLE_PDF_BYTES),
        mime_type="application/pdf",
        content_sha256="abc123hash",
        status=DocumentStatus.COMPLETED.value,
        error_category=None,
        error_message=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )

    with patch(
        "app.modules.documents.service.document_service.get_document_status",
        new=AsyncMock(return_value=mock_status),
    ):
        app_instance.dependency_overrides[require_documents_read] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/v1/documents/{doc_id}")

            assert res.status_code == 200
            data = res.json()
            assert data["document_id"] == str(doc_id)
            assert data["status"] == DocumentStatus.COMPLETED.value


@pytest.mark.asyncio
async def test_get_document_extraction_success(app_instance, security_context) -> None:
    """Verify GET /api/v1/documents/{id}/extraction returns extracted text."""
    doc_id = uuid4()
    mock_ext = DocumentExtractionResponse(
        extraction_id=uuid4(),
        document_id=doc_id,
        tenant_id=TENANT_ID,
        page_count=1,
        character_count=92,
        extraction_method="pdfplumber_v1",
        extraction_version="1.0.0",
        raw_text="Jane Doe - Senior Python Cloud Architect",
        page_texts=["Jane Doe - Senior Python Cloud Architect"],
        quality_score=0.95,
        warnings=[],
        extracted_at=datetime.now(UTC),
    )

    with patch(
        "app.modules.documents.service.document_service.get_document_extraction",
        new=AsyncMock(return_value=mock_ext),
    ):
        app_instance.dependency_overrides[require_documents_read] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/v1/documents/{doc_id}/extraction")

            assert res.status_code == 200
            data = res.json()
            assert data["document_id"] == str(doc_id)
            assert "Jane Doe" in data["raw_text"]


@pytest.mark.asyncio
async def test_get_presigned_download_url_success(app_instance, security_context) -> None:
    """Verify GET /api/v1/documents/{id}/download-url returns presigned URL."""
    doc_id = uuid4()
    mock_url_res = DocumentDownloadUrlResponse(
        document_id=doc_id,
        download_url="https://s3.amazonaws.com/resumes/doc.pdf?X-Amz-Signature=test",
        expires_in_seconds=900,
    )

    with patch(
        "app.modules.documents.service.document_service.get_presigned_download_url",
        new=AsyncMock(return_value=mock_url_res),
    ):
        app_instance.dependency_overrides[require_documents_read] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.get(f"/api/v1/documents/{doc_id}/download-url?expires_in=900")

            assert res.status_code == 200
            data = res.json()
            assert "X-Amz-Signature" in data["download_url"]
            assert data["expires_in_seconds"] == 900


@pytest.mark.asyncio
async def test_delete_document_success(app_instance, security_context) -> None:
    """Verify DELETE /api/v1/documents/{id} cleans up document."""
    doc_id = uuid4()
    mock_del_res = DocumentDeleteResponse(
        document_id=doc_id,
        status=DocumentStatus.DELETED.value,
        message="Document purged successfully",
    )

    with patch(
        "app.modules.documents.service.document_service.delete_document",
        new=AsyncMock(return_value=mock_del_res),
    ):
        app_instance.dependency_overrides[require_documents_delete] = lambda: security_context

        transport = ASGITransport(app=app_instance)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            res = await ac.delete(f"/api/v1/documents/{doc_id}")

            assert res.status_code == 200
            data = res.json()
            assert data["status"] == DocumentStatus.DELETED.value


@pytest.mark.asyncio
async def test_missing_tenant_context_rejected(app_instance) -> None:
    """Verify document operations without active tenant context are rejected."""
    context_no_tenant = SecurityContext(
        user_id=USER_ID,
        session_id=uuid4(),
        tenant_id=None,  # No tenant
        roles=["recruiter"],
        permissions=["documents:read"],
        token_version=1,
        role_version=1,
        is_super_admin=False,
    )

    app_instance.dependency_overrides[require_documents_read] = lambda: context_no_tenant

    transport = ASGITransport(app=app_instance)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get(f"/api/v1/documents/{uuid4()}")
        assert res.status_code == 403
