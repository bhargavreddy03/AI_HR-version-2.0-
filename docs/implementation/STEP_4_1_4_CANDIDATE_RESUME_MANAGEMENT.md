# STEP 4.1.4 — CANDIDATE RESUME MANAGEMENT IMPLEMENTATION REPORT
## AI HR INTELLIGENCE PLATFORM — ENTERPRISE SAAS

---

### Executive Summary

Step 4.1.4 (**Candidate Resume Management**) has been implemented as an enterprise-grade, candidate-facing document management system fully integrated with the pre-existing **Step 3.10 Secure Document Ingestion Pipeline** and **Foundational Skill Registry**.

The implementation strictly enforces candidate-level tenant isolation, IDOR defense, private S3 object storage, cryptographic deduplication, immutable version history defensibility for submitted job applications, structured profile extraction, and accurate status representation regarding production OCR and antivirus capabilities.

---

### 1. Architectural Integration with Step 3.10

Rather than constructing a separate or duplicate document processing pipeline, Step 4.1.4 directly reuses and extends the Step 3.10 enterprise services:

1. **Storage Service (`StorageService`)**:
   - Manages private S3 bucket storage under isolated candidate prefixes: `candidates/{user_id}/resumes/{year}/{month:02d}/{random_name}`.
   - Enforces SHA-256 integrity verification upon write.
   - Generates time-limited (900s / 15-minute) presigned download URLs for authenticated candidate owners only.
2. **Document Ingestion Security (`file_security.py`)**:
   - Supported extensions: strictly validated `.pdf` and `.docx`.
   - File size ceiling: 10 MB maximum upload boundary.
   - Executable payload elimination: rejects DOS/Windows PE, Linux ELF, Mach-O, Java class, HTML, SVG, and shell scripts.
   - PDF deep validation: `%PDF-` magic header enforcement, detection of active JavaScript triggers (`/JavaScript`, `/JS`, `/Launch`, `/EmbeddedFiles`).
   - OpenXML DOCX deep validation: `PK\x03\x04` magic header, anti-zip bomb decompression ratio protection ($\le 20.0$, uncompressed limit 50 MB, entry count $\le 500$), and anti-directory traversal (`..`).
   - Malware scanning: integrates with `BaseMalwareScanner` (fail-closed in staging/production; accurate disclosure of development mode scanner).
3. **Extraction Services**:
   - **PDF Extractor (`PDFExtractorService`)**: Modular `pdfplumber` extractor with page count limits and timeout boundaries.
   - **DOCX Extractor (`DocxExtractorService`)**: Standard OpenXML paragraph extractor using `zipfile` and `defusedxml.ElementTree` without unsafe binary dependencies.
4. **Canonical Skill Registry & Matcher (`SkillRegistry`, `ExactMatcher`)**:
   - Resolves resume keywords against canonical skill aliases and taxonomy nodes, avoiding false positives.

---

### 2. Version History & Regulatory Defensibility

In recruitment compliance (EEOC, OFCCP, GDPR), historical candidate submissions must remain legally defensible. Changing or uploading a new resume version must never mutate previous job application records.

1. **Cryptographic Snapshot Pinning**:
   - When a candidate applies to a job, `job_applications.resume_snapshot_sha256` records the exact content digest of the resume submitted.
   - `job_applications.resume_id` links the application to the specific versioned `CandidateResume` record.
2. **Version Lineage**:
   - Uploading a new resume automatically calculates `version_number = existing_count + 1`.
   - The first resume uploaded is automatically designated default (`is_default = True`).
   - Candidates can designate any version as their active default; only one resume can be default at any given time.
3. **Deletion Defensibility & Retention Enforcement**:
   - When a candidate requests resume deletion via `DELETE /api/v1/resumes/{resume_id}`:
     ```python
     app_res = await db.execute(
         select(func.count(JobApplication.id)).where(
             (JobApplication.resume_id == resume.id)
             | (JobApplication.resume_snapshot_sha256 == resume.content_sha256)
         )
     )
     if app_count > 0:
         raise ValidationException(
             f"Cannot delete resume '{resume.filename}' (version {resume.version_number}): "
             f"This document is retained under compliance and audit rules because it is associated with "
             f"{app_count} submitted job application(s).",
             code="ERR_RESUME_RETAINED_FOR_APPLICATIONS",
         )
     ```
   - If referenced by submitted applications, deletion is blocked, protecting evidence from accidental destruction.
   - In the frontend UI, retained resumes display an **Application Retained** badge with a lock icon. Attempting to delete triggers an informative defensibility modal explaining compliance preservation rules.
   - Resumes not linked to submitted applications are cleanly purged from S3 and PostgreSQL. If the deleted resume was default, default status is automatically promoted to the newest remaining version.

---

### 3. Structured Resume Extraction & Verification Workflow

Step 4.1.4 implements structured extraction across 9 key candidate profile fields:

- **Name**: Extracted from document header lines.
- **Email**: Extracted via RFC-compliant regex.
- **Phone**: Extracted via international and domestic phone pattern regex.
- **Summary**: Extracted from summary/objective sections.
- **Skills**: Extracted using the canonical skill taxonomy and matcher.
- **Experience**: Parsed into title, organization, date range, and bullet points.
- **Education**: Parsed into degrees, institutions, and completion years.
- **Certifications**: Parsed from credentials and licensing headers.
- **Projects**: Parsed into titles and descriptions.

#### Verification & Profile Synchronization
- Candidates can open the **Candidate Extraction Review & Verification** modal to review parsed data.
- Clear distinction:
  - Extracted skills are tagged with **Verified** once vetted or corrected by the candidate.
  - Candidates can add missing skills or delete erroneous items.
  - One-click **Apply to Verified Profile** button promotes reviewed resume skills directly into the candidate's permanent global profile (`CandidateUserProfile.self_declared_skills`).

---

### 4. Accurate Capability & Status Representation

Conforming to prompt requirements, the application inspects and accurately reports environment capabilities rather than fabricating claims of deep OCR or enterprise antivirus scanning:

1. **OCR Status**:
   - `ocr_applied`: `false`
   - `ocr_provider`: `"null_ocr_unconfigured"`
   - UI Notice: *"Direct digital text extraction active for native PDF and Word (.docx) documents. Scanned image OCR is currently unconfigured in this deployment; image-only resumes will require text-layer documents."*
2. **Malware Status**:
   - `malware_scan_status`: `"passed_development_mode"`
   - Accurately identifies that standard format, executable header, and size validation passed under development scanner fallbacks.

---

### 5. API Endpoints Specification

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/resumes/upload` & `/me/upload` | Upload PDF or DOCX resume, compute SHA-256, extract text/skills, store in S3. |
| `GET` | `/api/v1/resumes` & `/me` | List candidate resumes with version numbers, default flags, and `has_active_applications` status. |
| `GET` | `/api/v1/resumes/{id}` & `/me/{id}` | Retrieve single resume metadata (IDOR protected). |
| `GET` | `/api/v1/resumes/{id}/extraction` & `/me/{id}/extraction` | Retrieve full structured extraction (Name, Email, Phone, Summary, Skills, Experience, Education, Certifications). |
| `PATCH` | `/api/v1/resumes/{id}/extracted-data` | Candidate corrections to extracted skills and text snapshot. |
| `POST` | `/api/v1/resumes/{id}/sync-profile` | Apply reviewed resume skills directly to verified profile. |
| `POST` | `/api/v1/resumes/{id}/set-default` | Designate active default resume for job applications. |
| `GET` | `/api/v1/resumes/{id}/download-url` | Generate time-limited presigned S3 download URL (expires in 900s). |
| `DELETE` | `/api/v1/resumes/{id}` | Delete resume (strictly protected by application defensibility retention checks). |

---

### 6. Automated Test Results

#### Backend Test Suite (`pytest`):
- `backend/tests/test_candidate_portal.py`: **25 passed in 1.70s** (100% pass rate)
  - `test_upload_resume_success_and_deduplication`
  - `test_resume_idor_prevention`
  - `test_resume_download_url_and_deletion`
  - `test_resume_deletion_blocked_when_linked_to_application` *(New Defensibility Test)*
  - `test_upload_docx_resume_and_extraction` *(New OpenXML DOCX Test)*
  - `test_resume_extraction_structured_fields_and_ocr_status` *(New Structured Extraction & OCR Test)*
  - `test_sync_resume_skills_to_profile` *(New Profile Synchronization Test)*
- `backend/tests/test_document_ingestion.py` & `test_security_foundation.py`: **70 passed in 1.32s** (Zero regression)

#### Frontend Test Suite (`vitest`):
- `frontend/src/__tests__/candidate_portal.test.tsx`: **19 passed in 700ms** (Total frontend: 44 tests passed across 8 test suites)
  - Renders resumes with version badges (`v1`, `v2`), default badge, and capability notice.
  - Opens application retention protection modal when deleting retained resume.
  - Opens review extraction modal and allows editing skills.
  - Dropzone validation of PDF and DOCX formats.
- Frontend TypeScript check (`tsc --noEmit`): **Clean, 0 errors**.

---

### 7. Scope Discipline & HARD STOP

- **Candidate Resume Management**: Completed.
- **AI Matching Engine**: Not started (strictly scoped for subsequent steps).
- **Recruiter Workflows**: Not started.
- **Awaiting User Review**: Ready for independent evaluation and approval.
