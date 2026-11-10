# STEP 4.2.2 — HR DASHBOARD AND RECRUITMENT OVERVIEW

## Overview & Architecture Alignment

Step 4.2.2 delivers the organization-scoped **HR / Recruiter Dashboard and Analytics Workspace** within the AI HR Intelligence Platform. Built upon the verified modular monolith and multi-tenant security architecture, the dashboard provides real-time recruitment metrics, conversion funnel analytics, and application velocity tracking.

All aggregations execute strictly within the active organization boundary (`WHERE tenant_id == :tenant_id`), completely prohibiting cross-tenant data leakage or hardcoded production figures.

---

## 1. High-Level KPI Recruitment Metrics

The dashboard calculates 10 core organization-scoped metrics derived from actual database records:

| Metric | Calculation Definition | Purpose |
|---|---|---|
| **Total Candidates** | `COUNT(DISTINCT candidate_id)` across all organization applications | Unique talent pool size |
| **Total Applications** | `COUNT(id)` on `job_applications` for this tenant | Overall application volume |
| **Active Jobs** | `COUNT(id)` on `jobs` where `status = 'published'` & deadline active | Open opportunities accepting candidates |
| **Published Jobs** | Total requisitions with `status = 'published'` | Active and closing requisitions |
| **Draft Jobs** | Total requisitions with `status IN ('draft', 'pending_approval')` | In-progress requisitions |
| **Awaiting Review** | Applications with `status IN ('submitted', 'under_review', 'applied')` | Immediate recruiter triage queue |
| **Shortlisted Candidates** | Applications with `status = 'shortlisted'` | Vetted talent ready for assessment |
| **Scheduled Interviews** | Applications with `status IN ('interviewing', 'interview_stage')` | Active evaluation rounds |
| **Hired Candidates** | Applications with `status IN ('hired', 'offer_accepted')` | Successfully closed roles |
| **Pending Tasks** | Actionable review items requiring recruiter attention | Operational backlog |

---

## 2. Visualizations & Analytical Charts

All visualizations are rendered dynamically via Recharts using backend-aggregated data:

1. **Recruitment Funnel Conversion**:
   - Progressive conversion pipeline: `Applied` → `Resume Review` → `Screening` → `Shortlisted` → `Interview Round` → `Offer Extended` → `Hired`.
   - Displays real candidate counts and step conversion percentages with division-by-zero safeguards for new organizations.
2. **Application Volume Over Time**:
   - Daily application submission velocity (`func.to_char(applied_at, 'YYYY-MM-DD')`) rendered as an indigo gradient area chart.
3. **Department Distribution**:
   - Application volume and active requisition counts grouped by department.
4. **Active Requisitions Breakdown**:
   - Table displaying title, department, total applications, and active candidates in pipeline.

---

## 3. Dynamic Filter Engine

Filters directly modify backend SQL queries rather than client-side array manipulation:
- **Time Horizon**: Past 7 Days, Past 30 Days, Past 90 Days, or All Time (`applied_at >= :start_date`).
- **Department**: Case-insensitive substring match (`Job.department ILIKE :dept`).
- **Job ID**: Specific requisition UUID filtering.
- **Application Stage**: Exact stage matching (`submitted`, `under_review`, `shortlisted`, etc.).

---

## 4. Security & Multi-Tenant Boundary Enforcement

1. **Tenant Resolution**:
   - `resolve_hr_tenant_context` dependency extracts `tenant_id` from trusted JWT claims or queries active `organization_memberships`.
   - Never trusts client-supplied tenant identifiers.
2. **Role Authorization**:
   - Restricts access strictly to authorized organizational roles (`recruiter`, `hiring_manager`, `org_admin`, `platform_super_admin`).
   - Unaffiliated candidates are rejected with RFC 7807 `403 Forbidden` (`HR_TENANT_MEMBERSHIP_REQUIRED`).
3. **Empty Tenant Resilience**:
   - New organizations with 0 jobs and 0 applications return clean 0 metrics and empty lists without runtime exceptions.

---

## 5. API Contracts

- **Endpoint**: `GET /api/v1/hr/dashboard/overview`
- **Query Parameters**: `start_date`, `end_date`, `department`, `job_id`, `location`, `employment_type`, `stage`.
- **Response Model**: `HrDashboardOverviewResponse`
- **Tag**: `HR & Recruiter Portal`

---

## 6. Verification Evidence

### 6.1 Backend Tests (`backend/tests/test_hr_dashboard.py`)
- `test_hr_dashboard_overview_metrics_calculation`: PASSED.
- `test_hr_dashboard_empty_organization_handling`: PASSED.
- `test_hr_dashboard_filters_application`: PASSED.
- `test_resolve_hr_tenant_context_blocks_unauthorized_users`: PASSED.
- `test_resolve_hr_tenant_context_allows_recruiter_and_org_admin`: PASSED.
- **Coverage**: 96% test coverage across `app.modules.hr`.
- **Regression Suite**: 131 passed out of 131.

### 6.2 Frontend Tests (`frontend/src/__tests__/hr_dashboard.test.tsx`)
- `renders all HR navigation links and organization context`: PASSED.
- `triggers onClose callback on mobile`: PASSED.
- `renders organization pill and user profile`: PASSED.
- `toggles profile menu with Sign Out`: PASSED.
- `renders all high-level KPI metric cards`: PASSED.
- `renders recruitment funnel conversion stages`: PASSED.
- `updates filters and triggers backend request`: PASSED.
- `renders empty state cleanly when organization has 0 applicants`: PASSED.
- **Total Frontend Tests**: 9 test files passed, 70 component tests passed.
- **TypeScript**: `tsc --noEmit` — 0 errors.
- **ESLint**: `next lint` — 0 errors, 0 warnings.
