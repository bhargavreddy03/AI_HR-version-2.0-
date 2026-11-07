# Resume Processing Pipeline Specification

This document defines the multi-tier resume ingestion, document validation, text extraction, OCR fallback, and structured skill parsing pipeline.

---

## 1. End-to-End Processing Pipeline

```mermaid
flowchart TD
    Upload["1. PDF Uploaded via Presigned S3 URL"] --> Validate["2. Document Validation (MIME, Magic Bytes, 15MB Limit)"]
    Validate --> AV["3. Malware Scan (ClamAV / AWS GuardDuty S3)"]
    AV --> TextExtract["4. Primary Text Extraction (pdfplumber)"]
    
    TextExtract --> ScannedCheck{"Extracted Characters >= 100?"}
    ScannedCheck -->|Yes: Digital PDF| Normalize["5. Text Cleaning & Whitespace Normalization"]
    ScannedCheck -->|No: Scanned / Image PDF| OCR["5. OCR Fallback (AWS Textract / Tesseract)"]
    OCR --> Normalize

    Normalize --> SkillExtract["6. Skill Extraction (SkillRegistry + ExactMatcher + Regex)"]
    SkillExtract --> MetadataExtract["7. Heuristic Metadata Parsing (Name, Years Exp)"]
    MetadataExtract --> VectorGen["8. Vector Embedding Generation (1536 dims)"]
    VectorGen --> Persistence["9. Persist to candidate_documents, candidate_skills & embeddings"]
    Persistence --> EventNotify["10. Emit Real-time SSE/WebSocket Event to Recruiter"]
```

---

## 2. Text Extraction & OCR Evaluation

| Feature / Criteria | Tier 1: `pdfplumber` (In-Process Worker) | Tier 2A: AWS Textract (Cloud Managed) | Tier 2B: Tesseract (Self-Hosted Worker) |
|:---|:---|:---|:---|
| **Primary Use Case** | Native digital PDFs with embedded text fonts | Scanned images, complex multi-column layouts, low-res scans | Scanned PDFs on air-gapped / cost-sensitive deployments |
| **Throughput & Speed** | Extremely fast ($< 0.5\text{ s}$ per resume) | Moderate ($2.0 - 4.5\text{ s}$ per document) | Slow ($3.0 - 8.0\text{ s}$ per document on CPU) |
| **Cost Profile** | $0.00$ marginal infrastructure cost | $\$0.0015$ per page scanned | High CPU / RAM allocation on worker containers |
| **Accuracy on Scans**| Fails on scanned/image-only PDFs | Industry-leading OCR and layout detection | Moderate; struggles with multi-column table resumes |
| **Recommendation** | **Default Tier 1 Parser** | **Recommended Tier 2 OCR Fallback** | Secondary fallback if AWS Textract is unavailable |

### Execution Logic:
1. The Celery worker runs `pdfplumber.open(bytes)`. If total extracted non-whitespace text exceeds 100 characters, Tier 1 is marked successful.
2. If total extracted text is $<100$ characters, the document is flagged as a scanned image or rasterized PDF, automatically invoking Tier 2 (AWS Textract `StartDocumentTextDetection`).

---

## 3. Duplicate Detection & Version Management

1. **Cryptographic Checksum**: The SHA-256 hash of the binary file is computed upon upload.
2. **Duplicate Ingestion Handling**:
   - If a duplicate checksum is detected within the same candidate profile: The system informs the user and links the existing document record without duplicating S3 storage.
   - If a candidate uploads an updated resume for an existing profile: The previous document's `is_current_version` flag is set to `FALSE`, and the new document is linked as the active primary version.
