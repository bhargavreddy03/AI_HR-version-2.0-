# STEP 4.2.5 — APPLICANT AND CANDIDATE MANAGEMENT IMPLEMENTATION REPORT

**Executive Summary:**
Step 4.2.5 delivers the comprehensive HR Applicant and Candidate Management workspace for the AI HR Intelligence Platform. Built upon the modular multi-tenant architecture and reusing global candidate identities, profile records, and resume ingestion from Step 4.1, this release provides organization-authorized applicant listings, advanced multi-dimensional filtering and search, complete candidate portfolio access, time-limited presigned resume URLs with audit logging, side-by-side candidate comparison matrix preparation, and bulk recruiter assignments.

---

## 1. Architecture & Design Principles

### 1.1 Global Identity Reuse & Anti-Duplication
- Candidate global identity (`User` and `CandidateUserProfile`) is strictly reused without duplicating candidate identities or resume storage.
- A candidate's profile is accessible to an HR user **only if** the candidate has submitted an active application to a job within the recruiter's organization.
- Cross-tenant candidate privacy is enforced: recruiters from Organization A cannot access applications or candidate profiles belonging to Organization B (`AuthorizationException(code="CANDIDATE_ACCESS_FORBIDDEN")`).
- Candidate application history is strictly scoped to the active tenant organization; candidates' applications to third-party organizations are invisible.

### 1.2 Secure Resume Access
- Reuses Step 3.10 `StorageService` for secure document storage.
- Never exposes public or permanent resume URLs.
- Generates 15-minute, time-limited presigned download URLs on demand.
- Records immutable audit logging entries on resume access in `JobApplication.audit_metadata["resume_access_history"]` and in the internal activity timeline.

---

## 2. Backend Implementation

### 2.1 Pydantic v2 Schemas (`backend/app/modules/hr/applicant_schemas.py`)
- `ApplicantListItem`: Comprehensive applicant row with candidate identity, contact information, applied job requisition, status badges, calculated professional experience years, verified skills, and resume availability.
- `ApplicantListResponse`: Server-side paginated envelope (`items`, `total`, `page`, `page_size`, `pages`).
- `CandidateDetailResponse`: Complete candidate portfolio view including work experience, education, certifications, projects, languages, current application context, and separated timelines.
- `ApplicationDetailContext`: Contextual application view with answers, cover letter, resume snapshot SHA-256, and strict separation between `candidate_timeline` and `internal_timeline`.
- `ResumeSignedUrlResponse`: Presigned URL download envelope (`download_url`, `content_sha256`, `expires_in_seconds`).
- `CandidateComparisonRequest` & `CandidateComparisonResponse`: Side-by-side evaluation matrix comparing 2 to 4 candidates on experience, education, skills match, missing competencies, and match percentages.
- `BulkRecruiterAssignRequest` & `BulkRecruiterAssignResponse`: Safe bulk assignment of lead recruiters to organization applications.

### 2.2 Service Layer (`backend/app/modules/hr/applicant_service.py`)
- `HrApplicantService`:
  - `list_applicants`: Server-side paginated query joining `JobApplication`, `Job`, `User`, `CandidateUserProfile`, and `CandidateResume`. Filters by job requisition, department, status, location, experience range, skills, and application date. Computes experience years via `calculate_experience_years()`.
  - `get_candidate_details`: Enforces candidate privacy barrier. Assembles full portfolio records (experiences, educations, certifications, projects, languages) and partitions timeline events into candidate-facing versus internal HR activity.
  - `get_resume_signed_url`: Verifies tenant boundary and candidate ownership before generating S3 presigned URL; logs access in audit metadata and internal timeline.
  - `compare_candidates`: Validates all requested applications belong to the same tenant organization; computes matching/missing skills against job requirements and evaluates match percentage.
  - `bulk_assign_recruiter`: Validates recruiter membership in the active organization and records assignment in internal application timeline.

### 2.3 API Endpoints (`backend/app/modules/hr/router.py`)
- `GET /api/v1/hr/applicants`: List applicants with server-side filters, search, and pagination.
- `GET /api/v1/hr/candidates/{candidate_id}`: Retrieve candidate profile and portfolio scoped strictly to organization context.
- `GET /api/v1/hr/applications/{application_id}/resume`: Generate short-lived presigned download URL for submitted resume with audit logging.
- `POST /api/v1/hr/candidates/compare`: Generate side-by-side comparison matrix for 2 to 4 candidates.
- `POST /api/v1/hr/applicants/bulk-assign`: Bulk-assign lead recruiter to selected organization applications.

---

## 3. Frontend Implementation

### 3.1 Applicant Pool Workspace (`frontend/src/app/hr/applicants/page.tsx`)
- **Responsive Table**: Displays candidate name, headline, location, applied role, department, calculated experience years, top skills pills, stage badge, resume PDF trigger, and application date.
- **Search & Filters**: Search by candidate name, email, or role; filter dropdowns for job openings, application stage, and minimum experience; dynamic sorting by application date or candidate name.
- **Selection Action Bar**: Checkbox multi-select supporting bulk recruiter assignment and opening the Candidate Comparison matrix when 2 to 4 candidates are selected.
- **Candidate Comparison Modal**: Side-by-side evaluation table comparing current roles, total experience years, education level, matching job skills, missing skills, match percentage bar, and resume access.
- **Bulk Assign Recruiter Modal**: Organization-authorized recruiter assignment with live member selection.

### 3.2 Candidate Detail Workspace (`frontend/src/app/hr/candidates/[id]/page.tsx`)
- **Header & Summary**: Candidate full name, headline, bio, contact details, work authorization, portfolio links, and quick summary metrics.
- **Submitted Resume Action**: Secure download button invoking presigned URL generation.
- **Portfolio Sections**: Professional work experience, education history, certifications, projects, and languages.
- **Separated Timelines**:
  - *Internal HR Activity & Notes*: Private recruitment updates, stage changes, and internal logs.
  - *Candidate-Facing Journey*: Transparent application progress visible to candidate.
- **Organization Application History**: Scoped view of all applications submitted by this candidate strictly within the current employer organization.

---

## 4. Verification & Testing

### 4.1 Backend Pytest (`backend/tests/test_hr_applicants.py`)
- `test_experience_years_calculation`: Verifies cumulative date calculation across roles.
- `test_applicant_listing_tenant_scoped`: Tests tenant boundary, pagination, and metadata aggregation.
- `test_candidate_details_retrieval_and_application_context`: Tests full portfolio assembly and timeline separation.
- `test_cross_tenant_candidate_privacy_blocked`: Validates `CANDIDATE_ACCESS_FORBIDDEN` when accessing non-applicant candidates.
- `test_resume_presigned_download_url_and_audit_logging`: Tests presigned URL generation and audit log persistence.
- `test_resume_access_cross_tenant_rejected`: Tests cross-tenant resume denial.
- `test_candidate_comparison_matrix`: Tests comparative skill matching and matrix generation.
- `test_bulk_recruiter_assignment`: Tests bulk recruiter assignment and membership verification.

**Backend Test Results**:
- `test_hr_applicants.py`: 8/8 passed in 0.80s.
- All HR suites (`test_hr_*.py`): 30/30 passed.
- Complete backend suite (HR + Candidate Portal): 73/73 passed.

### 4.2 Frontend Vitest (`frontend/src/__tests__/hr_applicants.test.tsx`)
- Renders applicant pool listing with candidate rows, status badges, and skills.
- Filters and search reload handling.
- Multi-select and Candidate Comparison matrix modal rendering.
- Bulk recruiter assignment modal and submission.
- Presigned resume URL download handling.
- CandidateDetailPage full profile, portfolio, and separated timelines rendering.

**Frontend Test Results**:
- `hr_applicants.test.tsx`: 6/6 passed.
- Complete HR frontend test suite: 27/27 passed in 6.91s.
- Typecheck: 0 TypeScript errors (`tsc --noEmit`).
- Lint: 0 ESLint warnings (`next lint`).
