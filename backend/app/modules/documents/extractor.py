"""Modular PDF text extraction service using pdfplumber conforming to Step 3.10.

Includes page-level extraction, resource limits, quality metrics, and scanned PDF detection.
"""

from __future__ import annotations

import hashlib
import io
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import pdfplumber

from app.core.errors import AppException

logger = logging.getLogger(__name__)

# Resource limits protecting against parser exhaustion and denial-of-service
MAX_PAGE_COUNT_LIMIT: Final[int] = 50
MAX_EXTRACTION_DURATION_SECONDS: Final[float] = 15.0
MAX_EXTRACTED_CHAR_LIMIT: Final[int] = 500_000
MIN_TEXT_PER_PAGE_THRESHOLD: Final[int] = 20  # Minimum characters to consider a page text-bearing


class ExtractionException(AppException):
    """Raised when PDF extraction fails due to format, encryption, or resource constraints."""

    def __init__(self, message: str = "PDF text extraction failed", code: str = "ERR_EXTRACTION_FAILED") -> None:
        super().__init__(message=message, status_code=422, code=code)


class PDFEncryptedException(ExtractionException):
    """Raised when an uploaded PDF is password-protected or encrypted."""

    def __init__(self, message: str = "Password-protected or encrypted PDFs are not supported") -> None:
        super().__init__(message=message, code="ERR_PDF_ENCRYPTED")


class PDFResourceLimitException(ExtractionException):
    """Raised when a PDF exceeds page or extraction resource bounds."""

    def __init__(self, message: str = "PDF exceeds allowable extraction resource limits") -> None:
        super().__init__(message=message, code="ERR_PDF_RESOURCE_EXHAUSTED")


# Backward-compatible exception aliases
PDFExtractorError = ExtractionException
PDFEncryptedError = PDFEncryptedException
PDFCorruptError = ExtractionException


@dataclass(frozen=True)
class PDFExtractionResult:
    """Consistent, structured result contract for document text extraction."""

    raw_text: str
    page_count: int
    page_texts: list[str]
    character_count: int
    quality_score: float
    warnings: list[str]
    requires_ocr: bool
    is_scanned: bool
    content_sha256: str
    extraction_method: str
    extraction_version: str
    extraction_timestamp: datetime
    duration_ms: float


class PDFExtractorService:
    """Production-grade PDF text extraction service with safety controls and telemetry."""

    EXTRACTION_METHOD: Final[str] = "pdfplumber_v1"
    EXTRACTION_VERSION: Final[str] = "1.0.0"

    def extract_from_bytes(
        self,
        file_bytes: bytes,
        max_pages: int = MAX_PAGE_COUNT_LIMIT,
        max_duration: float = MAX_EXTRACTION_DURATION_SECONDS,
    ) -> PDFExtractionResult:
        """Extract text from raw PDF bytes enforcing page bounds, timeouts, and OCR checks."""
        start_time = time.perf_counter()
        content_sha256 = hashlib.sha256(file_bytes).hexdigest()
        warnings: list[str] = []

        if not file_bytes:
            raise ExtractionException("Cannot extract text from empty document bytes")

        stream = io.BytesIO(file_bytes)
        try:
            with pdfplumber.open(stream) as pdf:
                page_count = len(pdf.pages)

                # Page count limit check
                if page_count > max_pages:
                    raise PDFResourceLimitException(
                        f"Document contains {page_count} pages, which exceeds the limit of {max_pages}"
                    )

                if page_count == 0:
                    warnings.append("Document contains 0 pages")
                    return self._create_empty_result(content_sha256, warnings, 0.0)

                page_texts: list[str] = []
                total_chars = 0
                low_text_pages_count = 0

                for page_idx, page in enumerate(pdf.pages):
                    # Timeout check during multi-page extraction
                    elapsed = time.perf_counter() - start_time
                    if elapsed > max_duration:
                        warnings.append(
                            f"Extraction duration limit reached ({elapsed:.1f}s > {max_duration:.1f}s); truncated at page {page_idx + 1}"
                        )
                        break

                    try:
                        text = page.extract_text() or ""
                    except Exception as page_exc:
                        logger.warning("Error extracting text on page %d: %s", page_idx + 1, page_exc)
                        text = ""
                        warnings.append(f"Failed to parse text on page {page_idx + 1}")

                    stripped = text.strip()
                    page_len = len(stripped)
                    total_chars += page_len
                    page_texts.append(text)

                    if page_len < MIN_TEXT_PER_PAGE_THRESHOLD:
                        low_text_pages_count += 1

                    if total_chars > MAX_EXTRACTED_CHAR_LIMIT:
                        warnings.append(
                            f"Extracted character limit ({MAX_EXTRACTED_CHAR_LIMIT}) exceeded; truncating remaining text"
                        )
                        break

                raw_combined = "\n\n".join(page_texts).strip()
                total_chars = len(raw_combined)

                # Scanned / OCR detection heuristics
                # If total text is minimal (<50 chars) or >=70% of pages are low-text
                is_scanned = (total_chars < 50) or (page_count > 0 and (low_text_pages_count / page_count) >= 0.7)
                requires_ocr = is_scanned

                if requires_ocr:
                    warnings.append("Document appears to be scanned or contains insufficient extractable text; OCR required")

                # Quality score calculation: evaluates ratio of alphanumeric/printable characters to total
                if total_chars == 0:
                    quality_score = 0.0
                else:
                    printable_count = sum(1 for ch in raw_combined if ch.isalnum() or ch.isspace())
                    base_ratio = printable_count / total_chars
                    completeness = min(1.0, total_chars / 200.0)
                    quality_score = round(base_ratio * completeness, 2)

                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

                return PDFExtractionResult(
                    raw_text=raw_combined,
                    page_count=page_count,
                    page_texts=page_texts,
                    character_count=total_chars,
                    quality_score=quality_score,
                    warnings=warnings,
                    requires_ocr=requires_ocr,
                    is_scanned=is_scanned,
                    content_sha256=content_sha256,
                    extraction_method=self.EXTRACTION_METHOD,
                    extraction_version=self.EXTRACTION_VERSION,
                    extraction_timestamp=datetime.now(UTC),
                    duration_ms=duration_ms,
                )

        except pdfplumber.pdfminer.pdfdocument.PDFPasswordIncorrect as exc:
            raise PDFEncryptedException("PDF is encrypted with a password and cannot be extracted") from exc
        except pdfplumber.pdfminer.pdfparser.PDFSyntaxError as exc:
            raise ExtractionException(f"Corrupted or invalid PDF structure: {exc}") from exc
        except PDFResourceLimitException:
            raise
        except Exception as exc:
            logger.error("Unexpected error during PDF extraction: %s", exc)
            raise ExtractionException(f"Failed to extract text from PDF: {exc}") from exc

    def _create_empty_result(
        self,
        content_sha256: str,
        warnings: list[str],
        duration_ms: float,
    ) -> PDFExtractionResult:
        """Helper to construct a typed empty result."""
        return PDFExtractionResult(
            raw_text="",
            page_count=0,
            page_texts=[],
            character_count=0,
            quality_score=0.0,
            warnings=warnings,
            requires_ocr=True,
            is_scanned=True,
            content_sha256=content_sha256,
            extraction_method=self.EXTRACTION_METHOD,
            extraction_version=self.EXTRACTION_VERSION,
            extraction_timestamp=datetime.now(UTC),
            duration_ms=duration_ms,
        )


# Global singleton instance
pdf_extractor_service = PDFExtractorService()


def get_pdf_extractor_service() -> PDFExtractorService:
    """Return default singleton instance of PDFExtractorService."""
    return pdf_extractor_service

