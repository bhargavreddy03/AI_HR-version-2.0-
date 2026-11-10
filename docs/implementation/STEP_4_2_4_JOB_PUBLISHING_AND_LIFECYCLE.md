# STEP 4.2.4 — JOB PUBLISHING AND LIFECYCLE MANAGEMENT IMPLEMENTATION REPORT

**Executive Summary:**
Step 4.2.4 delivers the full enterprise-grade job publishing and governed lifecycle workflow for the AI HR Intelligence Platform. Built upon the foundation of Step 4.2.3, this release implements a finite state machine (FSM) enforcing transition rules, strict separation of duties (SoD) preventing self-approval by drafting recruiters, mandatory feedback reasons on revision requests, audit history tracking via an immutable `job_lifecycle_history` table, asynchronous notification dispatch with Celery idempotency, public discovery visibility filters, and an interactive Kanban/stepper-driven UI in the HR Portal.

---

## 1. Database & Schema Architecture

### 1.1 Alembic Migration 008 (`008_job_publishing_and_lifecycle.py`)
- **Revision ID**: `008_job_publishing_lifecycle`
- **Down Revision**: `007_job_requisitions`
- **Columns Added to `jobs`**:
  - `closed_at`: `sa.DateTime(timezone=True)`, nullable
  - `reopened_at`: `sa.DateTime(timezone=True)`, nullable
  - `change_request_reason`: `sa.Text()`, nullable
- **New Table Created: `job_lifecycle_history`**:
  - `id`: `postgresql.UUID(as_uuid=True)`, primary key (UUIDv7)
  - `tenant_id`: `postgresql.UUID(as_uuid=True)`, nullable=False, indexed, FK `organizations.id` (CASCADE)
  - `job_id`: `postgresql.UUID(as_uuid=True)`, nullable=False, indexed, FK `jobs.id` (CASCADE)
  - `previous_status`: `sa.String(50)`, nullable=False
  - `new_status`: `sa.String(50)`, nullable=False
  - `action`: `sa.String(50)`, nullable=False
  - `actor_id`: `postgresql.UUID(as_uuid=True)`, nullable=False, indexed, FK `users.id` (RESTRICT)
  - `actor_role`: `sa.String(50)`, nullable=False
  - `reason`: `sa.Text()`, nullable
  - `audit_metadata`: `postgresql.JSONB()`, server_default=`'{}'`, nullable=False
  - `created_at`: `sa.DateTime(timezone=True)`, server_default=func.now(), nullable=False, indexed
- **Indexes**:
  - `ix_job_lifecycle_history_tenant_id`
  - `ix_job_lifecycle_history_job_id`
  - `ix_job_lifecycle_history_actor_id`
  - `ix_job_lifecycle_history_created_at`

### 1.2 Model Definition (`backend/app/modules/jobs/models.py`)
- `Job` updated with `closed_at`, `reopened_at`, `change_request_reason`, and relationship `lifecycle_history = relationship("JobLifecycleHistory", back_populates="job", order_by="desc(JobLifecycleHistory.created_at)", cascade="all, delete-orphan")`.
- `JobLifecycleHistory` model mapped with full tenant scoping, relationships to `Job`, `Organization`, and actor `User`.

---

## 2. Finite State Machine & Governance Rules

### 2.1 State Transition Matrix (`TRANSITION_RULES`)
The lifecycle service enforces the following transition graph:

| Action | From Status | To Status | Allowed Roles | Business Constraints |
| :--- | :--- | :--- | :--- | :--- |
| `submit_for_approval` | `draft` | `pending_approval` | `recruiter`, `hiring_manager`, `org_admin` | Moves draft into review queue |
| `approve` | `pending_approval` | `approved` | `hiring_manager`, `org_admin` | **Separation of Duties**: Recruiter cannot self-approve (`recruiter_id == user_id` blocked) |
| `request_changes` | `pending_approval` | `draft` | `hiring_manager`, `org_admin` | **Mandatory Feedback**: Requires non-empty reason explaining adjustments |
| `return_to_draft` | `approved` | `draft` | `recruiter`, `hiring_manager`, `org_admin` | Allows editing before publication |
| `publish` | `approved` | `published` | `recruiter`, `hiring_manager`, `org_admin` | Sets `published_at = utc_now()`, activates public discovery |
| `pause` | `published` | `paused` | `recruiter`, `hiring_manager`, `org_admin` | Temporarily suspends applications |
| `reopen` | `paused` | `published` | `recruiter`, `hiring_manager`, `org_admin` | Sets `reopened_at = utc_now()`, restores active applications |
| `close` | `published`, `paused` | `closed` | `recruiter`, `hiring_manager`, `org_admin` | Sets `closed_at = utc_now()`, rejects new applications |
| `archive` | `closed` | `archived` | `recruiter`, `hiring_manager`, `org_admin` | Long-term archival; read-only |

### 2.2 Separation of Duties (SoD) Policy
- When an `approve` action is attempted, the system compares `current_user.id` against `job.recruiter_id`.
- If identical, the operation is blocked with:
  ```python
  raise AuthorizationException(
      message="Separation of duties policy active: recruiter cannot approve their own job requisition.",
      error_code="SEPARATION_OF_DUTIES_VIOLATION",
  )
  ```
- Super-administrators (`is_super_admin=True`) may bypass SoD for emergency governance intervention.

### 2.3 Publication Behavior & Candidate Discovery Integration
- `JobService.list_jobs` enforces:
  - `Job.status == "published"`
  - `Job.visibility == "public"` (internal and unlisted jobs excluded from public candidate directory)
  - Non-expired deadline: `or_(Job.application_deadline.is_(None), Job.application_deadline > now)`
  - Drafts, pending_approval, paused, closed, and archived jobs are excluded from public search.
- `JobService.apply_to_job` enforces:
  - Validates `job.status == "published"`. Closed or archived jobs raise `ConflictException("This job is no longer accepting applications", error_code="JOB_NOT_ACCEPTING_APPLICATIONS")`.

---

## 3. Background Notifications & Celery Idempotency

### 3.1 Asynchronous Notification Task (`backend/app/modules/notifications/tasks.py`)
- Task `dispatch_job_lifecycle_notification(job_id, action, actor_id, ...)`:
  - Computes deterministic idempotency key based on job ID, action, and event timestamp to prevent duplicate notifications during network retries.
  - Resolves team recipients (lead recruiter and hiring manager).
  - Emits in-app `Notification` entities and queues email tasks where SMTP delivery is configured.

---

## 4. API Endpoints (`backend/app/modules/hr/router.py`)

- `POST /api/v1/hr/jobs/{job_id}/lifecycle`: Executes governed lifecycle transition with separation of duties enforcement and audit history recording.
- `GET /api/v1/hr/jobs/{job_id}/lifecycle/history`: Retrieves immutable chronological audit history entries with actor metadata and transition notes.
- `GET /api/v1/hr/jobs/{job_id}/lifecycle/permitted-actions`: Returns context-sensitive permitted actions and SoD status for the current user and job.

---

## 5. Frontend UI/UX (`frontend/src/app/hr/jobs/[id]/page.tsx`)

- **Publication & Approval Lifecycle Stepper**: Visual stages displaying 1. Draft Requisition, 2. Under Review, 3. Approved, 4. Published (or Paused/Closed).
- **Separation of Duties Alert Banner**: Informs recruiters when SoD is active and approval must come from a designated hiring manager or administrator.
- **Reviewer Feedback Banner**: Highlights requested changes and revision notes when returned to draft.
- **Contextual Action Buttons**: Dynamically displays valid action buttons (`Submit for Approval`, `Approve Requisition`, `Request Changes`, `Publish to Careers Site`, `Pause`, `Reopen`, `Close`, `Archive`) matching the backend permissions.
- **Modals**:
  - *Request Changes Modal*: Enforces mandatory feedback input before submission.
  - *Publish Modal*: Confirms visibility and application deadline terms before going live.
  - *Close Modal*: Warns about application termination and allows optional closing reason.
- **Lifecycle Audit History Timeline**: Displays full chronological audit trail with actors, roles, transition badges (`draft → pending_approval`), timestamps, and feedback notes.

---

## 6. Verification & Test Coverage

### 6.1 Backend Pytest (`backend/tests/test_hr_job_lifecycle.py`)
- `test_submit_draft_for_approval`: Verifies transition from `draft` to `pending_approval`.
- `test_separation_of_duties_blocks_recruiter_self_approval`: Confirms `SEPARATION_OF_DUTIES_VIOLATION` is raised when assigned recruiter attempts approval.
- `test_hiring_manager_approval_succeeds`: Confirms hiring manager can approve and record history.
- `test_request_changes_requires_mandatory_reason`: Validates rejection when reason is empty.
- `test_request_changes_with_valid_reason_returns_to_draft`: Tests return to draft and reason storage.
- `test_publish_approved_job_sets_timestamp`: Asserts `published_at` timestamp is set upon publication.
- `test_pause_reopen_and_close_lifecycle`: Tests full operational lifecycle (`pause` -> `reopen` -> `close`).
- `test_prohibited_transitions_rejected`: Validates FSM blocks illegal transitions (e.g. `draft` directly to `published`).
- `test_candidate_discovery_and_application_rejection_for_closed_job`: Verifies closed jobs reject candidate applications.

**Backend Suite Result**: 65/65 tests passed (22 HR suite tests).

### 6.2 Frontend Vitest (`frontend/src/__tests__/hr_job_lifecycle.test.tsx`)
- Renders stepper and permitted action buttons.
- Displays separation of duties warning banner when active and hides unauthorized approve button.
- Handles direct `approve` execution.
- Handles `request_changes` modal with mandatory feedback validation.
- Handles `publish` modal confirmation and timestamp display.
- Renders immutable lifecycle audit timeline with actors, transitions, and notes.

**Frontend Suite Result**: 21/21 HR tests passed; 0 TypeScript errors; 0 ESLint warnings.
