# STEP 4.2.6 — RECRUITMENT PIPELINE AND APPLICATION STAGE MANAGEMENT IMPLEMENTATION REPORT

**Executive Summary:**
Step 4.2.6 delivers the complete organization-scoped recruitment pipeline and Kanban board workflow for the AI HR Intelligence Platform. Built upon the modular multi-tenant architecture and reusing existing application and status-history foundations, this implementation introduces a strict Finite State Machine (FSM) transition matrix, organization-configurable workflow stages, optimistic concurrency control, mandatory rejection rationale, role-based transition gating, and safe automatic synchronization to candidate-facing statuses.

---

## 1. Architecture & Design Principles

### 1.1 Configurable Stages & Canonical Normalization
- Supports 11 canonical recruitment stages in standard workflow order:
  1. `applied`
  2. `resume_review`
  3. `screening`
  4. `shortlisted`
  5. `assessment`
  6. `interview`
  7. `final_interview`
  8. `offer`
  9. `hired` (terminal)
  10. `rejected` (terminal, reconsiderable with reason)
  11. `withdrawn` (terminal, protected candidate-initiated state)
- Supports organization-specific pipeline configurations stored in `organizations.pipeline_stages` JSONB column. When unconfigured, organizations gracefully fallback to standard canonical stages.
- Normalizes legacy/alternate stage aliases (e.g. `submitted` &rarr; `applied`, `in_screening` &rarr; `screening`, `under_review` &rarr; `resume_review`, `not_selected` &rarr; `rejected`).

### 1.2 Finite State Machine (FSM) Transition Matrix
- Arbitrary jumps between stages are strictly prohibited. Every transition is validated against `PIPELINE_TRANSITION_RULES`.
- Candidates who initiated withdrawal (`status == "withdrawn"`) are permanently locked and cannot be moved by recruiters (`APPLICATION_WITHDRAWN`).
- Candidates who have reached `hired` are in a terminal state and cannot be transitioned (`APPLICATION_HIRED_TERMINAL`).
- Rejections require non-empty rationale (`REJECTION_REASON_REQUIRED`) to maintain compliance and transparency.
- Moving to `offer` or `hired` requires elevated organizational authority (`hiring_manager`, `org_admin`, `admin`, or `platform_super_admin`); unauthorized recruiter transitions raise `INSUFFICIENT_STAGE_PERMISSIONS`.

### 1.3 Optimistic Concurrency Control & Audit Immutability
- Added `stage_version` (Integer, default 1) to `job_applications`. Each transition increments `stage_version`.
- Callers supply `expected_stage_version`. Any race condition or concurrent update by another recruiter raises `ConflictException(code="CONCURRENT_UPDATE_CONFLICT")`.
- Every transition appends an immutable audit record to `application_stage_history` tracking `previous_stage`, `new_stage`, `actor_id`, `actor_name`, `actor_role`, `reason`, and timestamp.

### 1.4 Safe Candidate-Facing Synchronization
- Internal recruitment stages automatically map to candidate-facing statuses (`applied` &rarr; `submitted`, `resume_review`/`screening` &rarr; `under_review`, `shortlisted`/`assessment`/`interview`/`final_interview` &rarr; `interview_scheduled`, `offer` &rarr; `offer_extended`, `hired` &rarr; `hired`, `rejected` &rarr; `rejected`).
- Internal rejection reasons and recruiter evaluation notes are **never** leaked to candidate portal interfaces.

---

## 2. Backend Implementation

### 2.1 Database & Migrations
- **Alembic Migration 009** (`backend/alembic/versions/009_recruitment_pipeline_and_stage_history.py`):
  - Adds `pipeline_stages` JSONB column to `organizations` table.
  - Adds `stage_version` (Integer, default 1) and `rejection_reason` (Text, nullable) to `job_applications` table.
  - Creates `application_stage_history` table with foreign keys to `job_applications` and `organizations`, indexed on `(tenant_id, application_id)` and `created_at`.
- **Database Models** (`backend/app/modules/jobs/models.py`, `backend/app/modules/organizations/models.py`):
  - Updated `JobApplication` with `stage_version`, `rejection_reason`, and `stage_history` relationship.
  - Added `ApplicationStageHistory` ORM model.
  - Added `pipeline_stages: Mapped[list[dict] | None]` to `Organization`.

### 2.2 Pydantic Schemas (`backend/app/modules/hr/pipeline_schemas.py`)
- `PipelineStageConfig`: Workflow stage definition (`id`, `label`, `order`, `is_terminal`, `color`).
- `PipelineCardItem`: Kanban application card with candidate details, job info, recruiter assignment, verified skills, and `stage_version`.
- `PipelineStageColumn`: Grouped Kanban column with count and cards.
- `PipelineBoardResponse`: Complete board response with columns, total candidates count, and active filters.
- `StageTransitionRequest` & `StageTransitionResponse`: Request and response envelopes for individual transitions with optimistic locking.
- `BulkStageMoveRequest` & `BulkStageMoveResponse`: Safe bulk stage move with per-application evaluation and skipped item summaries.
- `ApplicationStageHistoryItem`: Immutable transition log entry for audit trails.

### 2.3 Service Layer (`backend/app/modules/hr/pipeline_service.py`)
- `get_configured_stages`: Fetches organization-configured stages or returns standard defaults.
- `get_pipeline_board`: Assembles Kanban board grouped by stage with optional job requisition, recruiter, and candidate search filters.
- `transition_stage`: Enforces FSM transition matrix, role permissions, optimistic version locking, rejection rationale validation, and immutable history recording.
- `bulk_stage_move`: Iterates over selected applications, verifying each against FSM constraints. Valid applications are updated; ineligible applications are recorded with explicit skip reasons.
- `get_stage_history`: Returns ordered audit history of stage transitions.

### 2.4 API Router Endpoints (`backend/app/modules/hr/router.py`)
- `GET /api/v1/hr/pipeline/stages`: Retrieve organization-configured recruitment pipeline stages.
- `GET /api/v1/hr/pipeline/board`: Retrieve recruitment pipeline Kanban board grouped by stage.
- `POST /api/v1/hr/applications/{application_id}/stage`: Move candidate application to a permitted pipeline stage.
- `POST /api/v1/hr/pipeline/bulk-stage-move`: Bulk move candidate applications to target stage with transition verification.
- `GET /api/v1/hr/applications/{application_id}/stage/history`: Retrieve complete audit trail of stage transitions.

---

## 3. Frontend Implementation

### 3.1 Kanban Board (`frontend/src/app/hr/pipeline/page.tsx`)
- **Horizontally Scrollable Pipeline Canvas**: Renders 11 responsive stage columns with stage indicators, candidate count badges, and empty-state placeholders.
- **Filter Toolbar**:
  - Live candidate search bar.
  - Job requisition dropdown selector.
  - Recruiter dropdown filter.
  - Bulk select mode toggle and quick refresh action.
- **Interactive Kanban Cards**:
  - Direct clickable link to candidate profile.
  - Candidate headline, job title, and department badge.
  - Up to 3 top skill pills with overflow indicator.
  - Assigned recruiter display or "Unassigned" indicator.
  - Stage version indicator (`v1`, `v2`, etc.).
  - Transition trigger button ("Move") and history trigger button.

### 3.2 Stage Transition & Guardrail Modals
- **Single Stage Transition Modal**:
  - Dynamic target stage dropdown highlighting permitted transitions.
  - Elevated permission advisory for `offer` and `hired` stages.
  - Mandatory non-empty rejection reason input when `rejected` is selected.
  - Optimistic locking using `expected_stage_version` with conflict resolution messaging.
- **Bulk Stage Move Modal**:
  - Multi-candidate selection checkboxes.
  - Target stage selector with bulk rejection justification.
  - Summary dialog reporting successfully moved count and granular skip reasons for ineligible applications.
- **Stage History Audit Modal**:
  - Chronological transition audit logs showing timestamp, actor name/role, previous stage, new stage, and transition reasons.

---

## 4. Verification & Testing

### 4.1 Backend Pytest Verification
- `test_hr_pipeline.py`:
  - `test_get_configured_stages_default_and_custom`: PASSED
  - `test_pipeline_board_grouped_by_stage_with_cards`: PASSED
  - `test_valid_stage_transition_and_history_creation`: PASSED
  - `test_prohibited_stage_transition_rejected`: PASSED
  - `test_mandatory_rejection_reason_enforcement`: PASSED
  - `test_withdrawn_and_hired_protection`: PASSED
  - `test_optimistic_concurrency_conflict`: PASSED
  - `test_offer_and_hired_role_restrictions`: PASSED
  - `test_bulk_stage_move_evaluates_rules_per_application`: PASSED
  - `test_cross_tenant_pipeline_isolation`: PASSED
- Total backend test suite: **83 passed in 3.48s** across all HR and candidate test suites.
- Code quality: `ruff check` passed with zero errors or warnings.

### 4.2 Frontend Vitest Verification
- `hr_pipeline.test.tsx`:
  - `renders pipeline board with column headers and candidate cards`: PASSED
  - `filters board by candidate search query`: PASSED
  - `opens stage transition modal and validates mandatory rejection reason`: PASSED
  - `executes valid stage transition with optimistic locking version`: PASSED
  - `handles optimistic concurrency conflict error`: PASSED
  - `opens bulk selection mode, selects cards, and performs bulk stage move`: PASSED
  - `opens audit history drawer and displays stage transitions`: PASSED
- Total frontend test suite: **34 passed across 5 test suites**.
- Type checking: `tsc --noEmit` passed with 0 errors.
- Linting: `next lint` passed with 0 warnings or errors.

---

## 5. Summary of Deliverables

| Area | Component / File | Purpose |
|---|---|---|
| Migration | `backend/alembic/versions/009_recruitment_pipeline_and_stage_history.py` | Schema migration for pipeline stages, stage version, and history table |
| Models | `backend/app/modules/jobs/models.py`, `backend/app/modules/organizations/models.py` | ORM entities for `ApplicationStageHistory` and pipeline configurations |
| Schemas | `backend/app/modules/hr/pipeline_schemas.py` | Pydantic v2 schemas for pipeline board, transitions, bulk move, and history |
| Service | `backend/app/modules/hr/pipeline_service.py` | FSM rules, optimistic concurrency, and tenant-scoped pipeline logic |
| Router | `backend/app/modules/hr/router.py` | 5 REST endpoints for recruitment pipeline operations |
| Backend Tests | `backend/tests/test_hr_pipeline.py` | 10 unit and integration tests covering all transition guardrails |
| Frontend Types | `frontend/src/types/hr.ts` | Complete TypeScript interfaces for pipeline entities |
| Frontend API | `frontend/src/lib/hrApi.ts` | 5 typed API client methods for recruitment pipeline endpoints |
| Frontend Page | `frontend/src/app/hr/pipeline/page.tsx` | Kanban board UI with single & bulk transition modals and history viewer |
| Frontend Tests | `frontend/src/__tests__/hr_pipeline.test.tsx` | 7 Vitest tests for board rendering, filters, transitions, and modals |
| Documentation | `docs/implementation/STEP_4_2_6_RECRUITMENT_PIPELINE.md` | Comprehensive architectural and functional report |
