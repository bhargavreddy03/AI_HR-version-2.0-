"""Document ingestion security: magic bytes validation, active content detection, and malware scanner interface.

Enforces secure document boundaries for resume and file processing conforming to Architecture Document 13 and 16.
"""

from __future__ import annotations

import io
import logging
import os
import re
import uuid
import zipfile
from dataclasses import dataclass

from app.core.errors import ValidationException

logger = logging.getLogger(__name__)

# Maximum file size for candidate document uploads (10 MB default)
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB
MAX_DOCX_UNCOMPRESSED_BYTES = 50 * 1024 * 1024  # 50 MB
MAX_DOCX_COMPRESSION_RATIO = 20.0
MAX_ZIP_ENTRIES = 500

# Allowed canonical extensions
ALLOWED_EXTENSIONS: frozenset[str] = frozenset({"pdf", "docx", "txt"})

# Executable magic numbers that must never be permitted
DANGEROUS_MAGIC_NUMBERS: tuple[tuple[bytes, str], ...] = (
    (b"MZ", "DOS/Windows Executable (PE/EXE/DLL)"),
    (b"\x7fELF", "Linux ELF Binary"),
    (b"\xca\xfe\xba\xbe", "Java Class File / Mach-O Fat Binary"),
    (b"\xfe\xed\xfa\xce", "Mach-O 32-bit Binary"),
    (b"\xfe\xed\xfa\xcf", "Mach-O 64-bit Binary"),
    (b"\xce\xfa\xed\xfe", "Mach-O 32-bit Reverse Binary"),
    (b"\xcf\xfa\xed\xfe", "Mach-O 64-bit Reverse Binary"),
    (b"#!", "Shell Script / Executable Script"),
    (b"<html", "HTML Document / Web Script"),
    (b"<!doctype html", "HTML Document / Web Script"),
    (b"<script", "JavaScript / Web Script"),
    (b"<?php", "PHP Script"),
    (b"<svg", "SVG Image / XML Script Vector"),
)

# Active content patterns in PDF documents
PDF_ACTIVE_CONTENT_PATTERNS: tuple[bytes, ...] = (
    b"/JavaScript",
    b"/JS",
    b"/Launch",
    b"/EmbeddedFiles",
    b"/SubmitForm",
    b"/ImportData",
)


class FileSecurityException(ValidationException):
    """Raised when an uploaded document violates file security policies."""

    def __init__(self, message: str, code: str = "ERR_FILE_SECURITY_VIOLATION") -> None:
        super().__init__(message=message, code=code, error_code=code)


# ------------------------------------------------------------------------------
# 1. Malware Scanner Interface & Implementations
# ------------------------------------------------------------------------------


@dataclass(frozen=True)
class MalwareScanResult:
    """Outcome of malware inspection."""

    is_clean: bool
    threat_name: str | None = None
    scanned: bool = False
    details: str = "No scanner configured"


class BaseMalwareScanner:
    """Abstract interface for document malware inspection before pipeline ingestion."""

    async def scan(self, file_bytes: bytes, filename: str) -> MalwareScanResult:
        raise NotImplementedError


class NullMalwareScanner(BaseMalwareScanner):
    """Development fallback scanner.

    NOTE: Does not provide live antivirus protection. In production, configure
    an enterprise antivirus daemon (e.g., ClamAV, AWS GuardDuty, or Cloudmersive).
    """

    async def scan(self, file_bytes: bytes, filename: str) -> MalwareScanResult:
        logger.info(
            "NullMalwareScanner passed file '%s' (%d bytes) [Development Mode Only]",
            filename,
            len(file_bytes),
        )
        return MalwareScanResult(
            is_clean=True,
            threat_name=None,
            scanned=False,
            details="NullMalwareScanner development stub (no live AV engine)",
        )


_active_scanner: BaseMalwareScanner = NullMalwareScanner()


def get_malware_scanner() -> BaseMalwareScanner:
    """Return active malware scanner singleton."""
    return _active_scanner


def set_malware_scanner(scanner: BaseMalwareScanner) -> None:
    """Configure active malware scanner."""
    global _active_scanner
    _active_scanner = scanner


# ------------------------------------------------------------------------------
# 2. File Signature & Format Validation
# ------------------------------------------------------------------------------


def sanitize_filename(original_filename: str) -> str:
    """Validate and sanitize user-provided filename, preventing path traversal and null bytes."""
    if not original_filename or not isinstance(original_filename, str):
        raise FileSecurityException("Filename is missing or invalid")

    # Reject null bytes and path traversal patterns
    if "\x00" in original_filename:
        raise FileSecurityException("Filename contains invalid null bytes")

    # Strip directory components (both Unix and Windows slashes)
    basename = os.path.basename(original_filename.replace("\\", "/"))

    # Remove any leading dots to prevent hidden files
    clean = re.sub(r"^\.+", "", basename).strip()
    if not clean:
        clean = "unnamed_document"

    # Limit length
    if len(clean) > 255:
        ext = clean.rsplit(".", 1)[-1] if "." in clean else ""
        clean = clean[:240] + ("." + ext if ext else "")

    return clean


def generate_secure_storage_name(extension: str) -> str:
    """Generate cryptographically random, collision-free server-side storage filename."""
    ext = extension.lower().lstrip(".")
    return f"{uuid.uuid4().hex}_{uuid.uuid4().hex[:8]}.{ext}"


def validate_file_size(file_bytes: bytes, max_size_bytes: int = MAX_FILE_SIZE_BYTES) -> None:
    """Ensure uploaded file size does not exceed maximum allowable threshold."""
    size = len(file_bytes)
    if size == 0:
        raise FileSecurityException("Uploaded file is empty (0 bytes)")
    if size > max_size_bytes:
        raise FileSecurityException(
            f"File size ({size / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of {max_size_bytes / (1024 * 1024):.1f} MB"
        )


def check_dangerous_executables(header: bytes) -> None:
    """Reject payloads matching known executable or script signatures."""
    for magic, desc in DANGEROUS_MAGIC_NUMBERS:
        if header.startswith(magic) or (b"<" in magic and magic in header[:512].lower()):
            raise FileSecurityException(f"Unsupported and unsafe executable file detected: {desc}")


def validate_pdf_content(file_bytes: bytes) -> None:
    """Validate PDF file header, structure, and absence of malicious active executable streams."""
    if not file_bytes.startswith(b"%PDF-"):
        raise FileSecurityException("Invalid PDF: Missing standard '%PDF-' magic header")

    # Scan for active JavaScript or launch triggers in PDF streams
    header_and_trailer = file_bytes[:65536] + file_bytes[-65536:]
    for pattern in PDF_ACTIVE_CONTENT_PATTERNS:
        if pattern in header_and_trailer:
            logger.warning("Rejected PDF with active executable trigger: %s", pattern)
            raise FileSecurityException(
                f"Malicious active content or script trigger detected in PDF: {pattern.decode('ascii', errors='replace')}"
            )


def validate_docx_content(file_bytes: bytes) -> None:
    """Validate DOCX OpenXML structure and protect against zip decompression bombs."""
    if not file_bytes.startswith(b"PK\x03\x04"):
        raise FileSecurityException("Invalid DOCX: Missing standard ZIP/OpenXML magic header")

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zf:
            infolist = zf.infolist()
            if len(infolist) > MAX_ZIP_ENTRIES:
                raise FileSecurityException(
                    f"DOCX archive contains too many files ({len(infolist)} > {MAX_ZIP_ENTRIES})"
                )

            total_uncompressed = 0
            has_content_types = False
            has_word_dir = False

            for info in infolist:
                # Path traversal check within zip archive
                if ".." in info.filename or info.filename.startswith(("/", "\\")):
                    raise FileSecurityException(
                        "Malicious path traversal detected inside DOCX archive"
                    )

                total_uncompressed += info.file_size
                if info.filename == "[Content_Types].xml":
                    has_content_types = True
                if info.filename.startswith("word/"):
                    has_word_dir = True

            # Anti-decompression bomb check
            if total_uncompressed > MAX_DOCX_UNCOMPRESSED_BYTES:
                raise FileSecurityException(
                    f"DOCX uncompressed size ({total_uncompressed / (1024 * 1024):.1f} MB) exceeds maximum allowed limit"
                )

            compressed_size = max(len(file_bytes), 1)
            ratio = total_uncompressed / compressed_size
            if ratio > MAX_DOCX_COMPRESSION_RATIO:
                raise FileSecurityException(
                    f"Suspicious zip compression ratio detected ({ratio:.1f} > {MAX_DOCX_COMPRESSION_RATIO})"
                )

            if not has_content_types and not has_word_dir:
                raise FileSecurityException(
                    "Invalid DOCX: Missing OpenXML [Content_Types].xml structure"
                )
    except zipfile.BadZipFile as exc:
        raise FileSecurityException("Malformed or corrupted DOCX archive") from exc


def validate_txt_content(file_bytes: bytes) -> None:
    """Validate plain text file ensuring strict UTF-8/ASCII and no binary control or executable bytes."""
    # Check for null bytes
    if b"\x00" in file_bytes:
        raise FileSecurityException("Plain text document contains binary null bytes")

    try:
        text_content = file_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise FileSecurityException("Plain text document must be valid UTF-8 encoded text") from exc

    # Reject if it starts with executable script headers
    if text_content.startswith(("#!", "<?php", "<html", "<!doctype")):
        raise FileSecurityException("Unsupported script or HTML payload in text document")


async def validate_document_upload(
    file_bytes: bytes,
    original_filename: str,
    max_size_bytes: int = MAX_FILE_SIZE_BYTES,
) -> tuple[str, str]:
    """Execute complete document security validation pipeline.

    Returns:
        tuple[canonical_extension: str, secure_storage_name: str]
    """
    # 1. Size check
    validate_file_size(file_bytes, max_size_bytes=max_size_bytes)

    # 2. Filename validation
    clean_name = sanitize_filename(original_filename)
    if "." not in clean_name:
        raise FileSecurityException("File must have an explicit extension (.pdf, .docx, .txt)")

    ext = clean_name.rsplit(".", 1)[-1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise FileSecurityException(
            f"Unsupported file format '{ext}'. Allowed formats: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # 3. Check for dangerous executables
    check_dangerous_executables(file_bytes[:1024])

    # 4. Deep format validation based on magic bytes and content
    if ext == "pdf":
        validate_pdf_content(file_bytes)
    elif ext == "docx":
        validate_docx_content(file_bytes)
    elif ext == "txt":
        validate_txt_content(file_bytes)

    # 5. Malware scanning interface
    scanner = get_malware_scanner()
    scan_result = await scanner.scan(file_bytes, clean_name)
    if not scan_result.is_clean:
        logger.error("Malware scanner flagged file '%s': %s", clean_name, scan_result.threat_name)
        raise FileSecurityException(
            f"Malware or high-risk content detected in document: {scan_result.threat_name or 'Threat Detected'}",
            code="ERR_MALWARE_DETECTED",
        )

    # 6. Generate server-side random storage name
    storage_name = generate_secure_storage_name(ext)
    return ext, storage_name
