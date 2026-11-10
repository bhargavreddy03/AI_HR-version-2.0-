# STEP 4.1.5 — JOB DISCOVERY, SEARCH, DETAILS AND SAVED JOBS
## Candidate Portal Subsystem Implementation Documentation

---

### 1. Executive Summary

Step 4.1.5 delivers the production-ready candidate-facing job discovery, search, requisition inspection, and bookmarking subsystem for the AI HR Intelligence Platform. Built strictly upon existing enterprise multi-tenant database models and document/skill registries, this implementation enables global candidates to discover, evaluate, and track verified enterprise opportunities across tenant organizations with zero fabricated data, zero exposure of internal recruiter notes, and rigorous protection against XSS and IDOR vulnerabilities.

All development conforms to the strict scope boundaries: search, filtering, pagination, sorting, job detail view, and saved jobs are fully functional and tested, while application submission workflows remain scheduled for Step 4.1.6.

---

### 2. Architecture and Data Flow

```
+---------------------------------------------------------------------------------------------------------+
|                                           CANDIDATE CLIENT                                              |
|                                                                                                         |
|  [Find Jobs (/candidate/jobs)]   [Job Details (/candidate/jobs/:id)]   [Saved Jobs (/candidate/saved)]  |
+---------------------------------------------------------------------------------------------------------+
                                           |                     |
                  GET /jobs/search (filters, sort, page)         | POST /jobs/:id/save
                  GET /jobs/:id                                  | DELETE /jobs/:id/save
                                           v                     v
+---------------------------------------------------------------------------------------------------------+
|                                             FASTAPI BACKEND                                             |
|                                                                                                         |
|  1. Public/Open Opportunities Enforcement:                                                              |
|     - Filter: Job.status == JobStatus.PUBLISHED.value                                                   |
|     - Filter: (Job.application_deadline IS NULL OR Job.application_deadline >= NOW())                  |
|     - Prevents draft, pending approval, suspended, or expired jobs from ever appearing in open search. |
|                                                                                                         |
|  2. Rich-Text Sanitization:                                                                             |
|     - sanitize_rich_text() removes script, iframe, object, javascript: URLs, and event handlers.       |
|     - Preserves clean paragraph and formatting markup safely.                                           |
|                                                                                                         |
|  3. Dynamic Candidate Context Annotations:                                                             |
|     - is_saved: Checks if candidate currently bookmarked the job.                                       |
|     - has_applied: Checks existing JobApplication records for this candidate.                          |
|     - is_expired: Evaluates whether job deadline has passed.                                            |
|                                                                                                         |
|  4. Saved Jobs Deduplication & Isolation:                                                               |
|     - Enforces CandidateSavedJob candidate_id ownership.                                                |
|     - Deduplicates bookmark requests (idempotent duplicate prevention).                                 |
+---------------------------------------------------------------------------------------------------------+
                                           |
                                           v
+---------------------------------------------------------------------------------------------------------+
|                                    POSTGRESQL 16 / SQLALCHEMY 2.X                                       |
|                                                                                                         |
|  - Table: jobs (joined with organizations for verified display)                                         |
|  - Table: candidate_saved_jobs (isolated by candidate_id)                                               |
|  - Table: job_applications (queried to flag has_applied)                                                |
+---------------------------------------------------------------------------------------------------------+
```

---

### 3. Backend Implementation Details

#### 3.1 Strict Published & Active Enforcement
As required by the enterprise architecture, draft, internal, and expired opportunities are strictly excluded from open discovery:
```python
query_stmt = (
    select(Job, Organization.name.label("organization_name"))
    .outerjoin(Organization, Job.tenant_id == Organization.id)
    .where(Job.status == JobStatus.PUBLISHED.value)
    .where(or_(Job.application_deadline.is_(None), Job.application_deadline >= now))
)
```

#### 3.2 Multi-Term Backend Search & Filtering
- **Keyword Search**: Matches case-insensitively across `Job.title`, `Job.description`, `Job.department`, `Job.location`, `Organization.name`, and `Job.skills_required`.
- **Parametric Filters**:
  - `department`
  - `location`
  - `remote_type` (`remote`, `hybrid`, `onsite`)
  - `employment_type` (`full_time`, `part_time`, `contract`, `internship`)
  - `experience_level` (`Entry-level`, `Mid-level`, `Senior`, `Lead`, `Executive`)
  - `skills` (JSONB skill taxonomy matches)
  - `min_salary` and `max_salary` range filters
  - `posted_within_days` date range cutoffs (1 day, 7 days, 14 days, 30 days)
- **Deterministic Sorting & Pagination**:
  - `recent`: Order by `Job.published_at DESC`, `Job.id DESC` (tie-breaker)
  - `closing_soon`: Order by `Job.application_deadline ASC NULLS LAST`, `Job.id DESC`
  - `salary_high`: Order by `Job.salary_max DESC NULLS LAST`, `Job.id DESC`
  - Server-side `page` and `page_size` (1-100) with SQL `COUNT` total and total pages.

#### 3.3 Security & XSS Sanitization
Requisition descriptions and requirements are filtered through `sanitize_rich_text()` utilizing compiled regex patterns to neutralize `<script>`, `<iframe>`, `<object>`, inline event attributes (`onload=`, `onerror=`), and `javascript:` pseudo-protocols before serialization.

#### 3.4 Saved Jobs Subsystem
- `POST /jobs/{job_id}/save`: Validates job existence and checks `CandidateSavedJob` table to prevent duplicates.
- `DELETE /jobs/{job_id}/save`: Unbookmarks with HTTP 204 response.
- `GET /jobs/saved`: Returns candidate's bookmarked roles annotated with `is_expired` and `has_applied` flags.

---

### 4. Frontend Experience & Design System

The candidate portal frontend conforms to the established enterprise visual language (clean surfaces, subtle lavender and blue accents, rounded cards, restrained typography):

1. **Find Jobs Page (`/candidate/jobs`)**:
   - Dynamic search bar supporting keyword and location queries.
   - Collapsible filter drawer for work arrangement, employment type, experience level, required skills, salary ranges, and publication date cutoffs.
   - Quick sorting dropdown (Most Recent, Closing Soon, Highest Salary).
   - Requisition cards displaying organization name, location, department, arrangement badges, salary ranges, skills chips, publication date, application deadline, and bookmark toggle.
   - Visual `Applied` indicator for positions already submitted by the candidate.
   - Server-side pagination controls (Previous/Next, page counters, total opportunities indicator).
2. **Dedicated Job Detail Page (`/candidate/jobs/[id]`)**:
   - Full requisition view with back navigation and direct URL sharing.
   - Distinct status banners:
     - Warning banner if the position is expired or closed.
     - Confirmation banner if the candidate has already applied (with a link to My Applications).
   - Structured sections: Role Overview & Responsibilities, Qualifications & Requirements, Required Skills, Preferred Skills, and Verified Enterprise Requisition assurance.
3. **Saved Jobs Page (`/candidate/saved-jobs`)**:
   - List of bookmarked opportunities with saved dates.
   - Clear identification of closed/expired jobs and applied roles.
   - One-click bookmark removal with immediate cache update.
   - Direct link to full requisition view.

---

### 5. Automated Verification & Test Results

#### 5.1 Backend Tests (`backend/tests/test_candidate_portal.py`)
- `test_job_discovery_lists_only_published_jobs`: Verifies draft and expired roles are strictly excluded.
- `test_job_discovery_advanced_search_and_filters`: Validates multi-term search, remote filters, skill filtering, and salary ranges.
- `test_job_discovery_sorting_and_pagination`: Validates stable sorting (`recent`, `closing_soon`, `salary_high`) and pagination math.
- `test_saved_jobs_duplicate_prevention_and_applied_status`: Verifies deduplication and `has_applied` / `is_expired` annotations.
- **Backend Result**: **28 / 28 test suites PASSED (100% green)**.

#### 5.2 Frontend Tests (`frontend/src/__tests__/candidate_portal.test.tsx`)
- `CandidateJobsPage`: Tests search inputs, card rendering, filtering triggers, and bookmark toggles.
- `CandidateJobDetailPage`: Tests requisition loading, skills rendering, expired banner display, and applied badge display.
- `CandidateSavedJobsPage`: Tests saved list rendering, expired/applied badge identification, and bookmark deletion.
- **Frontend Result**: **8 test files, 52 / 52 test suites PASSED (100% green)**.
- **TypeScript Typecheck**: **0 errors (`tsc --noEmit` passed cleanly)**.

---

### 6. Scope Boundaries & Next Steps

This substage is strictly limited to job discovery, search, details, and saved jobs. Application submission workflows, resume selection with SHA-256 seal, and status tracking are deferred to **Step 4.1.6 (Application Submission Workflow)**.
