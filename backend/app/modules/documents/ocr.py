"""OCR fallback architecture and provider abstraction conforming to Step 3.10.

Provides modular interfaces for optical character recognition on scanned PDFs without
hardcoding paid third-party dependencies or misrepresenting unconfigured OCR as successful.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OCRResult:
    """Outcome of an OCR extraction execution."""

    executed: bool
    raw_text: str
    page_texts: list[str]
    character_count: int
    confidence_score: float
    provider_name: str
    error_message: str | None = None
    extracted_at: datetime = datetime.now(UTC)


class BaseOCRProvider(ABC):
    """Abstract interface for pluggable OCR extraction engines (e.g. AWS Textract, Tesseract)."""

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Return the unique provider name."""
        ...

    @abstractmethod
    async def extract_ocr_text(self, file_bytes: bytes) -> OCRResult:
        """Perform optical character recognition over supplied document bytes."""
        ...


class NullOCRProvider(BaseOCRProvider):
    """Default fallback when no production OCR engine is configured.

    Explicitly returns executed=False and empty text, ensuring documents requiring OCR
    are transitioned to OCR_REQUIRED rather than falsely classified as successfully scanned.
    """

    @property
    def provider_name(self) -> str:
        return "null_ocr_unconfigured"

    async def extract_ocr_text(self, file_bytes: bytes) -> OCRResult:
        logger.info(
            "NullOCRProvider invoked for %d bytes: external OCR engine is unconfigured",
            len(file_bytes),
        )
        return OCRResult(
            executed=False,
            raw_text="",
            page_texts=[],
            character_count=0,
            confidence_score=0.0,
            provider_name=self.provider_name,
            error_message="External OCR provider engine is not configured in this environment",
            extracted_at=datetime.now(UTC),
        )


class MockOCRProvider(BaseOCRProvider):
    """Deterministic mock OCR provider for unit and integration testing."""

    def __init__(self, mock_text: str = "Mock OCR extracted resume content", confidence: float = 0.95) -> None:
        self._mock_text = mock_text
        self._confidence = confidence

    @property
    def provider_name(self) -> str:
        return "mock_test_ocr"

    async def extract_ocr_text(self, file_bytes: bytes) -> OCRResult:
        return OCRResult(
            executed=True,
            raw_text=self._mock_text,
            page_texts=[self._mock_text],
            character_count=len(self._mock_text),
            confidence_score=self._confidence,
            provider_name=self.provider_name,
            error_message=None,
            extracted_at=datetime.now(UTC),
        )


# Singleton provider configuration
_active_ocr_provider: BaseOCRProvider = NullOCRProvider()


def get_ocr_provider() -> BaseOCRProvider:
    """Return active OCR provider instance."""
    return _active_ocr_provider


def set_ocr_provider(provider: BaseOCRProvider) -> None:
    """Configure active OCR provider (used for test fixtures or enterprise engine registration)."""
    global _active_ocr_provider
    _active_ocr_provider = provider
