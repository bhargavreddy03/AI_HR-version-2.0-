# STEP 4.1.6 — JOB APPLICATION SUBMISSION AND TRACKING
## Candidate Portal Subsystem Implementation Documentation

---

### 1. Executive Summary

Step 4.1.6 implements the production-grade candidate-facing application submission and tracking subsystem for the AI HR Intelligence Enterprise SaaS Platform. Built directly upon existing multi-tenant architecture, candidate identity, and secure document ingestion pipelines (Step 3.10 and Step 4.1.4), this subsystem enables authenticated candidates to review requisitions, select cryptographically verified resume versions, complete mandatory application questionnaires, declare statutory legal consents, and submit applications with database-enforced deduplication, transaction safety, and idempotency guarantees.

In addition, candidates can track their end-to-end application journey via the **My Applications** dashboard (`/candidate/applications`) and dedicated detail views (`/candidate/applications/[id]`). The tracking system presents a transparent, candidate-visible chronological timeline while strictly enforcing applicant data privacy: internal recruiter comments, confidential hiring ratings, and private match scores are completely quarantined and inaccessible to candidates.

---

### 2. Architecture and Data Flow

```
+-----------------------------------------------------------------------------------------------------------------+
|                                                 CANDIDATE CLIENT                                                |
|                                                                                                                 |
|  [Job Detail / Apply Modal]            [My Applications List]               [Application Detail View]           |
|  5-Step Submission Flow:               Filter Tabs:                         - Requisition Metadata              |
|  1. Requisition Overview               - All                                - Cryptographic SHA-256 Seal        |
|  2. Resume Version Select              - In Review                          - Official Timeline History         |
|  3. Application Questionnaire          - Interviewing                       - Candidate Answers Record          |
|  4. Statutory Consents                 - Concluded / Withdrawn              - Statutory Consents Declaration    |
|  5. SHA-256 Sealed Confirmation        Search & Quick Actions               - Permanent Withdrawal Option       |
+-----------------------------------------------------------------------------------------------------------------+
                                      |                                                 |
             POST /jobs/:id/apply     |                                                 | POST /jobs/applications/
             (with idempotency_key)   | GET /jobs/applications/me                       |      me/:id/withdraw
                                      v                                                 v
+-----------------------------------------------------------------------------------------------------------------+
|                                                 FASTAPI BACKEND                                                 |
|                                                                                                                 |
|  1. Multi-Step Eligibility Validation:                                                                          |
|     - Candidate authenticated & account active (`user.is_active`)                                               |
|     - Job exists, published, and accepting applications (`status == 'published'`)                              |
|     - Requisition deadline has not expired (`deadline is None or deadline >= now`)                             |
|     - Candidate profile exists and is initialized                                                               |
|     - Selected resume exists and candidate is confirmed owner (IDOR Protection)                                 |
|                                                                                                                 |
|  2. Duplicate & Idempotency Enforcement:                                                                        |
|     - Checks client-provided `idempotency_key` against existing submissions -> returns existing record safely    |
|     - Checks existing applications for candidate + job -> blocks duplicates (`ERR_DUPLICATE_APPLICATION`)       |
|     - Re-application for withdrawn roles blocked with historical preservation (`ERR_APPLICATION_WITHDRAWN`)     |
|                                                                                                                 |
|  3. Evidence Snapshotting & Audit Trail:                                                                        |
|     - Computes/retrieves SHA-256 digest of submitted resume version                                             |
|     - Records candidate responses: work authorization, visa sponsorship, earliest availability, cover letter    |
|     - Records statutory data processing consent and applicant accuracy certification timestamps                  |
|     - Initializes candidate timeline with `submitted` milestone                                                 |
|     - Database transactional commit catching concurrency race conditions (`IntegrityError` rollback)            |
|                                                                                                                 |
|  4. Strict Privacy Boundary:                                                                                    |
|     - `JobApplicationRead` schema strictly excludes recruiter notes, AI match score, and internal evaluations  |
+-----------------------------------------------------------------------------------------------------------------+
                                      |
                                      v
+-----------------------------------------------------------------------------------------------------------------+
|                                         POSTGRESQL 16 / ALEMBIC MIGRATION 005                                    |
|                                                                                                                 |
|  - Table: job_applications                                                                                      |
|    - resume_version_applied (INTEGER)                                                                           |
|    - answers (JSONB)                                                                                            |
|    - consent_records (JSONB)                                                                                    |
|    - timeline (JSONB)                                                                                           |
|    - idempotency_key (VARCHAR(128), INDEXED)                                                                    |
|    - audit_metadata (JSONB)                                                                                     |
|    - Unique Constraint: `uq_job_applications_candidate_job` (candidate_id, job_id)                             |
+-----------------------------------------------------------------------------------------------------------------+
```

---

### 3. Backend Implementation Details

#### 3.1 Database Migration (`005_application_submission_and_tracking.py`)
To capture candidate-provided questionnaires, versioned resume references, legal consents, and audit trails, Alembic migration `005` extends `job_applications`:
```python
def upgrade() -> None:
    op.add_column("job_applications", sa.Column("resume_version_applied", sa.Integer(), nullable=True))
    op.add_column("job_applications", sa.Column("answers", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("job_applications", sa.Column("consent_records", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("job_applications", sa.Column("timeline", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.add_column("job_applications", sa.Column("idempotency_key", sa.String(length=128), nullable=True))
    op.add_column("job_applications", sa.Column("audit_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
    op.create_index("ix_job_applications_idempotency_key", "job_applications", ["idempotency_key"], unique=False)
```

#### 3.2 Backend Service & Reliability Engineering (`service.py`)

##### A. Multi-Factor Eligibility Check
Before writing any database record, the backend validates:
1. **User Active**: `if not user or not user.is_active: raise HTTPException(403, "Account deactivated")`.
2. **Requisition Status**: `if job.status != JobStatus.PUBLISHED.value: raise HTTPException(400, "Position is not accepting applications")`.
3. **Application Deadline**: `if job.application_deadline and job.application_deadline < now: raise HTTPException(400, "Application deadline has passed")`.
4. **Resume Ownership (IDOR Protection)**: Verifies that the selected `resume_id` belongs directly to `candidate.id`. If mismatched, raises `HTTPException(404, "Selected resume not found or does not belong to candidate")`.

##### B. Idempotency & Safe Retry
Clients supply a unique `idempotency_key` (UUID v4) on submission. If network timeouts cause client retries, the service recognizes the identical idempotency key and returns the original confirmed submission without raising errors or duplicating records:
```python
if idempotency_key:
    existing_key_app = await db.scalar(
        select(JobApplication).where(JobApplication.idempotency_key == idempotency_key)
    )
    if existing_key_app:
        return _build_submit_response(existing_key_app)
```

##### C. Historical Record Preservation & Withdrawn Applications
The system enforces that historical application records are **never deleted**. If a candidate previously withdrew from a requisition, the historical submission remains permanently sealed in the database for auditability and compliance, and re-application is blocked under standard enterprise policy:
```python
if existing_app.candidate_status == "withdrawn":
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="You previously withdrew your application for this position. Re-application is not permitted.",
    )
```

##### D. Concurrency & Race Condition Handling
To prevent simultaneous race conditions when multiple submission requests arrive concurrently, the system pairs the database unique constraint `uq_job_applications_candidate_job` with an explicit `IntegrityError` rollback handler:
```python
try:
    await db.commit()
    await db.refresh(application)
except IntegrityError:
    await db.rollback()
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="An application for this position was submitted concurrently. Please refresh.",
    )
```

##### E. Application Withdrawal Protocol
Candidates may withdraw eligible applications. Business rules disallow withdrawal once terminal determinations (`rejected`, `not_selected`) or offer stages (`offer`, `offer_stage`) have been reached. Withdrawal requires a non-empty explanation (minimum 3 characters), transitions status to `withdrawn`, logs a timestamped milestone in the candidate timeline, creates a system notification, and **never deletes** the record.

---

### 4. Frontend Experience & UX Components

#### 4.1 Application Submit Modal (`ApplicationSubmitModal.tsx`)
A guided 5-step modal workflow with smooth transitions and step indicators:
1. **Requisition Overview**: Displays title, organization, department, work arrangement, and required skills.
2. **Resume Selection**: Lists all uploaded candidate resumes with version numbers, active/default badges, and upload timestamps.
3. **Application Questionnaire**: Captures legal work authorization status, visa sponsorship requirement, earliest start date / notice period, and tailored cover letter.
4. **Review & Statutory Consents**: Provides complete submission summary and requires explicit confirmation of:
   - *Statutory Data Processing Consent* (GDPR / EEOC).
   - *Applicant Truth and Accuracy Certification*.
5. **Confirmation & Sealed Evidence**: Displays success confirmation, cryptographic SHA-256 seal, and direct link to track progress in My Applications.

#### 4.2 My Applications Dashboard (`/candidate/applications`)
- **Status Tabs**: Fast filtering across `All`, `In Review`, `Interviewing`, and `Concluded / Withdrawn` with badge counters.
- **Parametric Search**: Live client search by job title or organization name.
- **Application Cards**: Presents requisition metadata, applied timestamp, `Resume v{N}` reference, cryptographic SHA-256 badge, candidate status badge, and contextual actions (`Details`, `Withdraw`).
- **Withdrawal Dialog**: Secure modal requiring candidate confirmation and reason input before dispatching withdrawal.

#### 4.3 Application Detail Page (`/candidate/applications/[id]`)
- **Header & Breadcrumbs**: Seamless navigation back to applications list, status badge, and requisition reference.
- **Audit Trail Timeline**: Step-by-step chronological progress tracker displaying milestones (`submitted`, `under_review`, `interview_stage`, `offer`, `withdrawn`).
- **Candidate Questionnaire Record**: Review of submitted work authorization, sponsorship, start date, and cover letter.
- **Compliance & Privacy Banner**: Reassurance that internal recruiter comments, AI match ratings, and private evaluations are strictly isolated.

---

### 5. Verification & Test Matrix

All backend and frontend tests pass cleanly with zero deprecation or assertion failures:

| Test Suite | Test Count | Status | Key Verifications Covered |
| :--- | :---: | :---: | :--- |
| **Backend Pytest** (`test_candidate_portal.py`) | 34 | **PASSED** | - Valid multi-step application submission<br>- Cryptographic SHA-256 seal recording<br>- Duplicate active application rejection<br>- Concurrency `IntegrityError` rollback<br>- Idempotency key replay verification<br>- Closed & expired requisition rejections<br>- Cross-candidate resume ownership (IDOR) rejection<br>- Withdrawn application historical preservation<br>- Mandatory reason withdrawal & stage restrictions |
| **Frontend Vitest** (`candidate_portal.test.tsx`) | 57 | **PASSED** | - Guided 5-step `ApplicationSubmitModal` flow<br>- Statutory checkbox validations<br>- Application list rendering with filter tabs<br>- Withdrawal dialog invocation & reason submission<br>- Application detail view timeline & responses rendering<br>- Zero recruiter note leak verification |
| **TypeScript Typecheck** (`tsc --noEmit`) | - | **PASSED** | Zero errors across all Next.js pages, components, and API client types |

---

### 6. Scope Boundary Compliance

In accordance with platform guidelines:
- Application submission, status tracking, candidate timeline, and withdrawal are fully implemented and verified.
- **HARD STOP**: Internal recruiter ATS pipeline, candidate evaluation stages, and hiring manager interfaces are scheduled for **Step 4.2 (Recruiter ATS)** and were not implemented here.
