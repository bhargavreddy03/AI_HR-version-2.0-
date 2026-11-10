# STEP 4.2.7 — RECRUITER AND HIRING MANAGER ASSIGNMENTS IMPLEMENTATION REPORT

**Executive Summary:**
Step 4.2.7 delivers organization-scoped recruitment assignments and team workload visibility for the AI HR Intelligence Platform. Building directly upon existing multi-tenant organization memberships and role-based access control (RBAC), this release establishes authorized recruiter and hiring manager assignments to job openings, immutable assignment audit tracking, idempotent notification dispatch, real-time database-driven capacity metrics, and strict tenant isolation without creating duplicate employee or membership tables.

---

## 1. Architecture & Design Principles

### 1.1 Existing Membership & RBAC Reuse
- Reuses `OrganizationMembership` and `Role` entities from Step 1.
- Never grants access simply because a user belongs to an organization.
- Assignment validation checks:
  - **Lead Recruiter Target**: Must be an active member of the active organization possessing a valid recruiter role (`recruiter`, `admin`, `org_admin`, or `platform_super_admin`). Unassigned users or invalid roles are rejected with `INVALID_RECRUITER_ROLE`.
  - **Hiring Manager Target**: Must be an active member of the active organization possessing a valid hiring manager role (`hiring_manager`, `admin`, `org_admin`, or `platform_super_admin`). Invalid roles are rejected with `INVALID_HIRING_MANAGER_ROLE`.
  - External users who do not belong to the organization are blocked with `USER_NOT_ORGANIZATION_MEMBER`.

### 1.2 Assignment Authority & Modification Permissions
- Authority to assign, reassign, or remove recruiter / hiring manager roles is restricted to:
  - Organization Admins (`org_admin`, `admin`, `platform_super_admin`).
  - The currently assigned lead recruiter for that job opening.
  - The currently assigned hiring manager for that job opening.
- Unassigned recruiters or unauthorized organization members cannot reassign jobs (`ASSIGNMENT_UNAUTHORIZED`).

### 1.3 Immutable Assignment History
- Introduces `job_assignment_history` table capturing every transition with:
  - `tenant_id`, `job_id`, `assignment_type` (`"recruiter"` or `"hiring_manager"`).
  - `actor_id` & `actor_name` (who performed the assignment).
  - `previous_user_id` & `previous_user_name` (previous assignee or null).
  - `new_user_id` & `new_user_name` (new assignee or null if unassigned).
  - `reason` (optional business rationale or handover note).
  - `created_at` (immutable timestamp).

### 1.4 Workload & Capacity Visibility
- Real-time aggregations computed directly from PostgreSQL tables (`jobs`, `job_applications`, `organization_memberships`):
  - Total assigned and active vacancies per team member.
  - Total candidate applications under their assigned openings.
  - Pending reviews count (applications in `applied`, `resume_review`, `screening`).
  - Active interviews count (applications in `interview`, `final_interview`).
  - Capacity indicator:
    - `critical`: &ge; 15 pending reviews or &ge; 8 active jobs.
    - `high`: &ge; 8 pending reviews or &ge; 5 active jobs.
    - `balanced`: &ge; 1 active job.
    - `low`: 0 assigned jobs.

### 1.5 Idempotent Notifications
- Triggers in-app alerts (`CandidateNotification`) and email delivery dispatch via `dispatch_candidate_email_notification`:
  - When assigned, the new recruiter or hiring manager receives an assignment alert.
  - When replaced or unassigned, the previous assignee receives a handover alert with the provided reason.
  - Handled safely with deduplication keys (`assignment:{job_id}:{event_type}:{user_id}`).

---

## 2. Backend Implementation

### 2.1 Database & Migrations
- **Alembic Migration 010** (`backend/alembic/versions/010_job_assignment_history.py`):
  - Creates `job_assignment_history` table with foreign keys to `organizations`, `jobs`, and `users`.
  - Indexed on `(tenant_id, job_id)` and `created_at`.
- **Database Models** (`backend/app/modules/jobs/models.py`):
  - Added `JobAssignmentHistory` ORM model.
  - Linked `assignment_history` relationship to `Job`.

### 2.2 Pydantic Schemas (`backend/app/modules/hr/assignment_schemas.py`)
- `AssignRecruiterRequest`: Target recruiter UUID and optional handover reason.
- `AssignHiringManagerRequest`: Target hiring manager UUID and optional reason.
- `JobAssignmentUpdateRequest`: Combined update payload.
- `JobAssignmentUpdateResponse`: Confirmation response with updated roles and timestamps.
- `JobAssignmentHistoryItem`: Historical audit log item.
- `UserWorkloadItem`: Workload metrics, pending counts, and capacity status.
- `TeamWorkloadResponse`: Summary breakdown for recruiters and hiring managers.
- `AssignedVacancyItem` & `AssignedVacanciesResponse`: Scoped vacancy list for authenticated user.

### 2.3 Service Layer (`backend/app/modules/hr/assignment_service.py`)
- `assign_recruiter`: Validates actor permissions, checks target recruiter membership & role, updates `job.recruiter_id`, appends immutable history, and dispatches notifications.
- `assign_hiring_manager`: Validates actor permissions, checks target hiring manager membership & role, updates `job.hiring_manager_id`, appends history, and dispatches notifications.
- `get_job_assignment_history`: Returns reverse-chronological transition logs for a vacancy.
- `get_team_workload`: Computes live database aggregations across active team members.
- `get_assigned_vacancies`: Queries vacancies assigned to the authenticated user.

### 2.4 API Router Endpoints (`backend/app/modules/hr/router.py`)
- `POST /api/v1/hr/jobs/{job_id}/assign-recruiter`
- `POST /api/v1/hr/jobs/{job_id}/assign-hiring-manager`
- `POST /api/v1/hr/jobs/{job_id}/assignments`
- `GET /api/v1/hr/jobs/{job_id}/assignments/history`
- `GET /api/v1/hr/assignments/workload`
- `GET /api/v1/hr/assignments/my-vacancies`

---

## 3. Frontend Implementation

### 3.1 Team & Assignments Workspace (`frontend/src/app/hr/assignments/page.tsx`)
- **Summary Cards**: Displays Total Assigned Vacancies, Unassigned Vacancies, Active Pipeline Candidates, and My Assigned Roles.
- **Team Workload & Capacity Tab**:
  - Live recruiter workload table with assigned jobs count, active candidates, pending review alerts, active interviews, and capacity badges.
  - Live hiring manager vacancy allocation table.
  - Search filter by team member name or email.
- **My Assigned Vacancies Tab**:
  - Scoped vacancy cards showing department, open position count, application funnel numbers, assigned counterpart, and direct links to Job Details and Pipeline Kanban.
- **Reassign Vacancy Modal**:
  - Select job opening, select lead recruiter, select hiring manager, optional handover reason.
- **Assignment Audit History Modal**:
  - Full audit trail showing actor, assignment type, previous assignee &rarr; new assignee, timestamp, and handover rationale.

### 3.2 Navigation & Requisition Integration
- Added **"Team & Assignments"** (`/hr/assignments`) to `HrSidebar`.
- Connected Job Details (`/hr/jobs/[id]`) "Recruitment Team Assignments" card with a direct link to manage assignments.

---

## 4. Verification & Testing

### 4.1 Backend Pytest Verification
- `test_hr_assignments.py`:
  - `test_assign_recruiter_success_and_history_and_notification`: PASSED
  - `test_assign_hiring_manager_success_and_history_and_notification`: PASSED
  - `test_unassign_recruiter_and_hiring_manager`: PASSED
  - `test_assignment_target_not_organization_member_rejected`: PASSED
  - `test_assignment_target_invalid_role_rejected`: PASSED
  - `test_unauthorized_user_cannot_reassign_job`: PASSED
  - `test_assigned_recruiter_can_reassign_own_job`: PASSED
  - `test_get_job_assignment_history_chronological`: PASSED
  - `test_get_team_workload_calculation_and_capacity_status`: PASSED
  - `test_get_my_assigned_vacancies`: PASSED
  - `test_cross_tenant_assignment_isolation`: PASSED
- Total backend test suite: **94 passed** in 1.44s across all HR and candidate test suites.
- Code quality: `ruff check` passed with zero errors or warnings.

### 4.2 Frontend Vitest Verification
- `hr_assignments.test.tsx`:
  - `renders recruitment team workload dashboard and summary metrics`: PASSED
  - `filters team members via search input`: PASSED
  - `switches to 'My Assigned Vacancies' tab and renders assigned vacancy cards`: PASSED
  - `opens reassign vacancy modal, selects new recruiter, and submits assignment update`: PASSED
  - `opens assignment audit history modal and displays past transitions`: PASSED
- Total frontend test suite: **39 passed across 6 test suites**.
- Type checking: `tsc --noEmit` passed with 0 errors.
- Linting: `next lint` passed with 0 warnings or errors.

---

## 5. Summary of Deliverables

| Area | Component / File | Purpose |
|---|---|---|
| Migration | `backend/alembic/versions/010_job_assignment_history.py` | Schema migration for job assignment history table |
| Models | `backend/app/modules/jobs/models.py` | `JobAssignmentHistory` model and `Job.assignment_history` relationship |
| Schemas | `backend/app/modules/hr/assignment_schemas.py` | Pydantic v2 schemas for assignments, workload, vacancies, and history |
| Service | `backend/app/modules/hr/assignment_service.py` | Membership validation, assignment logic, workload calculations, notifications |
| Router | `backend/app/modules/hr/router.py` | 6 REST endpoints for recruitment assignments and workload |
| Backend Tests | `backend/tests/test_hr_assignments.py` | 11 unit and integration tests covering role validation, history, and isolation |
| Frontend Types | `frontend/src/types/hr.ts` | TypeScript interfaces for assignment payloads, responses, and workload |
| Frontend API | `frontend/src/lib/hrApi.ts` | 6 typed API client methods for assignment endpoints |
| Frontend Page | `frontend/src/app/hr/assignments/page.tsx` | Workload dashboard, vacancy allocations, reassign modal, audit history modal |
| Navigation | `frontend/src/components/hr/HrSidebar.tsx` | Added Team & Assignments link to primary navigation |
| Requisition Integration | `frontend/src/app/hr/jobs/[id]/page.tsx` | Integrated team assignment management into Job Details view |
| Frontend Tests | `frontend/src/__tests__/hr_assignments.test.tsx` | 5 Vitest tests for workload, tabs, search, reassignment, and history |
| Documentation | `docs/implementation/STEP_4_2_7_RECRUITER_AND_HIRING_MANAGER_ASSIGNMENTS.md` | Comprehensive architectural and functional report |
