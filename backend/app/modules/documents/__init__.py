"""Domain Module: Documents & Secure Ingestion (Step 3.10).

S3-compatible object storage, PDF extraction, malware scanning, lifecycle state machine,
and OCR fallback architecture.
"""

from app.modules.documents.extractor import (
    ExtractionException,
    PDFCorruptError,
    PDFEncryptedError,
    PDFEncryptedException,
    PDFExtractionResult,
    PDFExtractorError,
    PDFExtractorService,
    PDFResourceLimitException,
    get_pdf_extractor_service,
)
from app.modules.documents.models import (
    VALID_DOCUMENT_TRANSITIONS,
    Document,
    DocumentExtraction,
    DocumentStatus,
    can_transition_document,
)
from app.modules.documents.ocr import (
    BaseOCRProvider,
    MockOCRProvider,
    NullOCRProvider,
    OCRResult,
    get_ocr_provider,
    set_ocr_provider,
)
from app.modules.documents.router import router
from app.modules.documents.schemas import (
    DocumentDeleteResponse,
    DocumentDownloadUrlResponse,
    DocumentExtractionResponse,
    DocumentStatusResponse,
    DocumentUploadResponse,
)
from app.modules.documents.service import DocumentService, document_service
from app.modules.documents.storage import (
    StorageError,
    StorageException,
    StorageIntegrityException,
    StorageService,
    get_storage_service,
    storage_service,
)
from app.modules.documents.tasks import (
    parse_document,
    process_document_task,
    recover_orphaned_documents_task,
)

__all__ = [
    "BaseOCRProvider",
    "Document",
    "DocumentDeleteResponse",
    "DocumentDownloadUrlResponse",
    "DocumentExtraction",
    "DocumentExtractionResponse",
    "DocumentService",
    "DocumentStatus",
    "DocumentStatusResponse",
    "DocumentUploadResponse",
    "ExtractionException",
    "MockOCRProvider",
    "NullOCRProvider",
    "OCRResult",
    "PDFCorruptError",
    "PDFEncryptedError",
    "PDFEncryptedException",
    "PDFExtractionResult",
    "PDFExtractorError",
    "PDFExtractorService",
    "PDFResourceLimitException",
    "StorageError",
    "StorageException",
    "StorageIntegrityException",
    "StorageService",
    "VALID_DOCUMENT_TRANSITIONS",
    "can_transition_document",
    "document_service",
    "get_ocr_provider",
    "get_pdf_extractor_service",
    "get_storage_service",
    "parse_document",
    "process_document_task",
    "recover_orphaned_documents_task",
    "router",
    "set_ocr_provider",
    "storage_service",
]
