# Step 2.8 — Final RLS-Aware User Deletion Guard and Cascade Protection Audit Report

## 1. Executive Summary & Design Scope

This audit report delivers the final technical reconciliation for **Step 2.8 — Final RLS-Aware User Deletion Guard Audit**, resolving the two outstanding database deletion-integrity findings identified during independent security review of the Step 2.7 architecture.

The report establishes two hardened database-level guarantees across the platform's multi-tenant PostgreSQL 16 schema:
1. **Cross-Tenant RLS-Aware Trigger Visibility**: Completely eliminates the cross-tenant data loss vulnerability where a `SECURITY INVOKER` trigger function was blind to records in other tenants due to `FORCE ROW LEVEL SECURITY`. Implements a least-privilege, dedicated non-login role (`aihr_deletion_guard_role`) with `BYPASSRLS` owning a hardened `SECURITY DEFINER` trigger function.
2. **Database-Enforced Upcoming Interview Cascade Protection**: Extends the database trigger guard to inspect `interview_participants` joined with `interview_schedules`, strictly preventing direct user deletions from cascading away active or upcoming interview panel assignments across any tenant.

### Strict Design-Only Rule Compliance:
- **No application source code was written or modified**.
- **No database migrations or tables were executed**.
- **No dependencies or packages were installed**.
- **No cloud infrastructure was provisioned**.
- **Step 3 has NOT begun**.
- All deliverables reside strictly as Markdown architecture documents inside `docs/architecture/`.

---

## 2. Finding 1: RLS Visibility Inside the User Deletion Trigger

### A. The Vulnerability Identified
The database trigger guard `fn_protect_user_cascade_deletion()` on the global `users` table queries tenant-scoped tables:
- `organization_memberships`
- `jobs`
- `interview_participants` / `interview_schedules`

All of these tenant-scoped tables enforce `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY` with the restrictive policy:
```sql
tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid
```

In PostgreSQL, trigger functions execute by default as `SECURITY INVOKER` with the privileges and RLS context of the current session role. When an application session is connected to Tenant A (`app.current_tenant_id = 'tenant-A'`):
1. An administrative or candidate deletion executes `DELETE FROM users WHERE id = :user_id`.
2. The trigger executes `SELECT 1 FROM organization_memberships WHERE user_id = OLD.id`.
3. Because of RLS filtering, PostgreSQL **only evaluates rows where `tenant_id = 'tenant-A'`**.
4. If the user holds active memberships, open jobs, or scheduled interviews in **Tenant B**, the query returns `0 rows`!
5. The trigger concludes that no blocking dependencies exist and returns `OLD`.
6. PostgreSQL proceeds with `DELETE FROM users`, and the database foreign keys (`ON DELETE CASCADE`) **silently delete all of the user's corporate memberships, interview assignments, and roles in Tenant B**!

### B. The Corrected Architecture: Dedicated Non-Login `BYPASSRLS` Guard Role

To enable cross-tenant verification without granting dangerous elevated privileges to the application login role or relying on superuser privileges, the platform establishes a **Least-Privilege `SECURITY DEFINER` Deletion Guard Architecture**:

```mermaid
flowchart TD
    subgraph ClientSession ["1. Ordinary Application Session (Tenant A Context)"]
        AppUser["Role: aihr_app_user<br/>(NOSUPERUSER, NOBYPASSRLS, RLS Strictly Enforced)"]
        DelStmt["DELETE FROM public.users WHERE id = :user_id"]
        AppUser --> DelStmt
    end

    subgraph TriggerBoundary ["2. PostgreSQL Trigger Invocation Boundary"]
        DelStmt --> Trg["BEFORE DELETE Trigger: trg_protect_user_cascade_deletion"]
        Trg --> SecDefiner["Function: fn_protect_user_cascade_deletion()<br/>SECURITY DEFINER<br/>search_path = pg_catalog, public, pg_temp"]
    end

    subgraph GuardRole ["3. Dedicated Non-Login Execution Context"]
        SecDefiner -.->|Executes as Owner| Guard["Owner Role: aihr_deletion_guard_role<br/>(NOLOGIN, NOINHERIT, BYPASSRLS, Read-Only)"]
        Guard --> CheckMemberships["SELECT 1 FROM public.organization_memberships<br/>(Inspects ALL tenants via BYPASSRLS)"]
        Guard --> CheckJobs["SELECT 1 FROM public.jobs<br/>(Inspects ALL tenants via BYPASSRLS)"]
        Guard --> CheckInterviews["SELECT 1 FROM public.interview_participants JOIN public.interview_schedules<br/>(Inspects ALL tenants via BYPASSRLS)"]
    end

    subgraph Decision ["4. Enforcement Decision"]
        CheckMemberships --> AnyFound{"Cross-Tenant Records Found?"}
        CheckJobs --> AnyFound
        CheckInterviews --> AnyFound
        
        AnyFound -->|Yes| Abort["RAISE EXCEPTION (restrict_violation)<br/>Transaction Aborted & Rolled Back"]
        AnyFound -->|No| Allow["RETURN OLD<br/>Safe Deletion Executes"]
    end
```

### C. Technical Security Specifications of the Deletion Guard:

1. **Role Separation & Zero Network Login (`NOLOGIN`)**:
   - `aihr_deletion_guard_role` is created with `NOLOGIN` and `NOINHERIT`. No client, user, or attacker can authenticate or open a connection as this role.
2. **Minimal Read-Only Privileges**:
   - `aihr_deletion_guard_role` is granted strictly `SELECT` permissions on only the 5 required verification tables (`organization_memberships`, `jobs`, `interview_participants`, `interview_schedules`, `interview_scorecards`).
   - It possesses **zero `INSERT`, `UPDATE`, or `DELETE` permissions** on any table. It cannot modify data.
3. **Restricted `BYPASSRLS` Scope**:
   - The `BYPASSRLS` attribute is assigned exclusively to `aihr_deletion_guard_role` solely so its read-only trigger queries can inspect child records across all tenant partitions.
   - The ordinary application role (`aihr_app_user`) has `NOBYPASSRLS` and remains 100% constrained by tenant RLS for all normal business queries.
4. **Hardened `search_path` & Anti-Shadowing Protections**:
   - The function explicitly specifies `SET search_path = pg_catalog, public, pg_temp`.
   - All table references are fully schema-qualified (`public.organization_memberships`, `public.jobs`, etc.), preventing schema-shadowing attacks by malicious temporary tables.
5. **Execution Permissions**:
   - Function execution is revoked from `PUBLIC` and granted specifically to `aihr_app_user`:
     ```sql
     REVOKE ALL ON FUNCTION public.fn_protect_user_cascade_deletion() FROM PUBLIC;
     GRANT EXECUTE ON FUNCTION public.fn_protect_user_cascade_deletion() TO aihr_app_user;
     ```

---

## 3. Finding 2: Upcoming Interview Participant Cascade Protection

### A. The Defect Identified
The relational schema defines:
```sql
interview_participants.user_id REFERENCES users(id) ON DELETE CASCADE
```
While the application-level deletion workflow checked upcoming interview schedules, the database trigger `fn_protect_user_cascade_deletion()` did not. If a direct SQL deletion or unverified background task executed `DELETE FROM users`, PostgreSQL would silently cascade and delete the user from upcoming scheduled interviews across any tenant, leaving interview panels unstaffed.

### B. The Exact Correction: Database-Enforced Upcoming Schedule Guard
The trigger function is extended to verify active and upcoming interview panel participation across all tenants:

```sql
-- 4. Block deletion if participant in upcoming scheduled interview(s) across ANY tenant
IF EXISTS (
    SELECT 1 
    FROM public.interview_participants ip
    JOIN public.interview_schedules s ON s.id = ip.interview_id
    WHERE ip.user_id = OLD.id 
      AND s.scheduled_at >= CURRENT_TIMESTAMP
      AND s.status IN ('scheduled', 'confirmed')
) THEN
    RAISE EXCEPTION 'Cannot hard-delete user %: assigned as participant in upcoming scheduled interview(s). User must be unassigned or interview rescheduled.', OLD.id
        USING ERRCODE = 'restrict_violation';
END IF;
```

### C. Complete Reconciliation of All User-Referencing Foreign Keys:

| # | Referencing Table | Relational Column | Foreign-Key Constraint & Behavior | Database Deletion Mechanism & Backstop | Rationale for Database Action |
|:---:|:---|:---|:---|:---|:---|
| 1 | `candidate_user_profiles` | `user_id` | `ON DELETE CASCADE` | **Allowed CASCADE** | Candidate-owned portfolio, resume drafts, and self-declared skills are safe to delete upon candidate account erasure. |
| 2 | `organization_memberships` | `user_id` | `ON DELETE CASCADE` | **STRICTLY REJECTED by DB Trigger Guard** (`BYPASSRLS`) | Corporate identity protection: prevents accidental wipe of employee/admin access across any tenant. |
| 3 | `candidate_profiles` | `user_id` | `ON DELETE SET NULL` | **Deliberate SET NULL** | Statutory compliance: employer candidate dossier is unlinked (`user_id = NULL`) and anonymized in place. |
| 4 | `jobs` | `hiring_manager_id` | `ON DELETE SET NULL` | **STRICTLY REJECTED by DB Trigger Guard** (`BYPASSRLS`) if active | Reassignment required: prevents published/open jobs from becoming unstaffed. Archived jobs allow `SET NULL`. |
| 5 | `screening_runs` | `created_by` | `ON DELETE SET NULL` | **Deliberate SET NULL** | Audit compliance: batch ML screening execution parameters and historical results are preserved. |
| 6 | `interview_participants` | `user_id` | `ON DELETE CASCADE` | **STRICTLY REJECTED by DB Trigger Guard** (`BYPASSRLS`) if upcoming | Operational integrity: upcoming interviews must be restaffed. Historical completed attendance cascades safely. |
| 7 | `interview_scorecards` | `interviewer_id` | **`ON DELETE RESTRICT`** | **STRICTLY REJECTED by PostgreSQL Relational Engine** | Statutory compliance (EEOC/OFCCP): scorecard evaluations must be retained. Triggers Account Scrambling & Deactivation. |
| 8 | `comments` | `author_id` | `ON DELETE SET NULL` | **Deliberate SET NULL** | Compliance audit: internal candidate evaluation discussion notes are preserved with author as "Former Employee". |
| 9 | `platform_audit_logs` | `actor_id` | `ON DELETE SET NULL` | **Deliberate SET NULL** | SOC 2 / ISO 27001 compliance: immutable administrative audit logs are preserved with `actor_id = NULL`. |
| 10 | `users` (Self) | `litigation_hold` | N/A (Column Flag) | **STRICTLY REJECTED by DB Trigger Guard** | Legal compliance: statutory holds strictly suspend all erasure and scrambling workflows. |

---

## 4. Final PostgreSQL 16 DDL Implementation

```sql
-- ============================================================================
-- 1. DEDICATED NON-LOGIN ROLE FOR RLS-AWARE DELETION GUARD
-- ============================================================================
CREATE ROLE aihr_deletion_guard_role WITH 
    NOLOGIN 
    NOINHERIT 
    NOSUPERUSER 
    NOCREATEDB 
    NOCREATEROLE 
    BYPASSRLS;

-- Grant minimal necessary read-only permissions across verified tables
GRANT SELECT ON public.organization_memberships TO aihr_deletion_guard_role;
GRANT SELECT ON public.jobs TO aihr_deletion_guard_role;
GRANT SELECT ON public.interview_participants TO aihr_deletion_guard_role;
GRANT SELECT ON public.interview_schedules TO aihr_deletion_guard_role;
GRANT SELECT ON public.interview_scorecards TO aihr_deletion_guard_role;

-- ============================================================================
-- 2. HARDENED SECURITY DEFINER TRIGGER FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION public.fn_protect_user_cascade_deletion()
RETURNS TRIGGER 
LANGUAGE plpgsql 
SECURITY DEFINER 
SET search_path = pg_catalog, public, pg_temp
AS $$
BEGIN
    -- 1. Block deletion if statutory litigation hold is flagged
    IF OLD.litigation_hold THEN
        RAISE EXCEPTION 'Cannot hard-delete user %: active statutory litigation hold.', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- 2. Block deletion if corporate organization memberships exist across ANY tenant (active or inactive)
    -- Operates under aihr_deletion_guard_role (BYPASSRLS) to inspect all tenants
    IF EXISTS (
        SELECT 1 
        FROM public.organization_memberships 
        WHERE user_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'Cannot hard-delete user %: corporate organization memberships exist across one or more tenants. User must be offboarded via corporate administrator workflow.', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    
    -- 3. Block deletion if assigned as hiring manager on active/open jobs across ANY tenant
    IF EXISTS (
        SELECT 1 
        FROM public.jobs 
        WHERE hiring_manager_id = OLD.id 
          AND status IN ('published', 'draft', 'internal')
    ) THEN
        RAISE EXCEPTION 'Cannot hard-delete user %: active job requisitions assigned as hiring manager. Jobs must be reassigned first.', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;

    -- 4. Block deletion if participant in upcoming scheduled interview(s) across ANY tenant
    IF EXISTS (
        SELECT 1 
        FROM public.interview_participants ip
        JOIN public.interview_schedules s ON s.id = ip.interview_id
        WHERE ip.user_id = OLD.id 
          AND s.scheduled_at >= CURRENT_TIMESTAMP
          AND s.status IN ('scheduled', 'confirmed')
    ) THEN
        RAISE EXCEPTION 'Cannot hard-delete user %: assigned as participant in upcoming scheduled interview(s). User must be unassigned or interview rescheduled.', OLD.id
            USING ERRCODE = 'restrict_violation';
    END IF;
    
    RETURN OLD;
END;
$$;

-- Transfer function ownership to the dedicated non-login role
ALTER FUNCTION public.fn_protect_user_cascade_deletion() OWNER TO aihr_deletion_guard_role;

-- Configure execution privileges
REVOKE ALL ON FUNCTION public.fn_protect_user_cascade_deletion() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.fn_protect_user_cascade_deletion() TO aihr_app_user;

-- ============================================================================
-- 3. ATTACH TRIGGER TO USERS TABLE
-- ============================================================================
CREATE TRIGGER trg_protect_user_cascade_deletion
BEFORE DELETE ON public.users
FOR EACH ROW
EXECUTE FUNCTION public.fn_protect_user_cascade_deletion();
```

---

## 5. Required 10-Scenario Validation Matrix

| # | Test Scenario | Attempted Action | Session Role & Tenant Context | Expected Database Behavior | Reason the System is Safe |
|:---:|:---|:---|:---|:---|:---|
| **1** | **User has memberships in another tenant** | `DELETE FROM users WHERE id = :id` | `aihr_app_user` with `app.current_tenant_id = 'tenant-A'` (Membership in Tenant B) | **Transaction Aborts**: SQLSTATE `23001` (restrict_violation) raised by trigger guard. | The `SECURITY DEFINER` function executes with `BYPASSRLS`, sees the Tenant B membership, and blocks deletion. |
| **2** | **User has active jobs in another tenant** | `DELETE FROM users WHERE id = :id` | `aihr_app_user` with `app.current_tenant_id = 'tenant-A'` (Job in Tenant B) | **Transaction Aborts**: SQLSTATE `23001` raised by trigger guard. | Trigger inspects all jobs across all tenants via `BYPASSRLS` and aborts deletion until job is reassigned. |
| **3** | **User has upcoming interview participation** | `DELETE FROM users WHERE id = :id` | `aihr_app_user` (Session in Tenant A, Interview in Tenant A or B) | **Transaction Aborts**: SQLSTATE `23001` raised by trigger guard. | Trigger checks `interview_participants` JOIN `interview_schedules` for `scheduled_at >= NOW()` and blocks cascade. |
| **4** | **User has historical scorecards** | `DELETE FROM users WHERE id = :id` | `aihr_app_user` or Direct Administrative SQL | **Transaction Aborts**: PostgreSQL core engine foreign key violation (`ON DELETE RESTRICT`). | Core relational engine blocks deletion directly at the schema level regardless of triggers or application logic. |
| **5** | **User has a litigation hold** | `DELETE FROM users WHERE id = :id` | Any role (Admin, App, or Worker) | **Transaction Aborts**: SQLSTATE `23001` raised by trigger guard. | Step 1 of the trigger evaluates `OLD.litigation_hold` and immediately aborts transaction. |
| **6** | **User has no corporate dependencies** | `DELETE FROM users WHERE id = :id` | `aihr_app_user` via candidate erasure workflow | **Success**: `candidate_user_profiles` cascades; `candidate_profiles` set to NULL; `users` row deleted. | All assertions in trigger pass; zero corporate data exists; safe to delete pure candidate identity. |
| **7** | **Deletion attempted by ordinary application role** | Direct `DELETE FROM users` bypass attempt | `aihr_app_user` with `NOBYPASSRLS` | **Trigger Guard Enforced**: All 4 checks execute via `SECURITY DEFINER`. | `aihr_app_user` cannot bypass the trigger; trigger executes as `aihr_deletion_guard_role`. |
| **8** | **Deletion attempted by background worker** | Celery task running maintenance SQL | Celery worker database connection | **Trigger Guard Enforced**: Same trigger fires on every row deletion. | Background workers are governed by the same PostgreSQL table trigger; cannot trigger cascading wipe. |
| **9** | **Deletion attempted through direct administrative SQL** | DBA or script issues `DELETE FROM users` | Admin connection (`aihr_app_user` or administrative role) | **Trigger Guard Enforced**: Trigger fires and aborts if memberships, jobs, or interviews exist. | Database trigger is engine-enforced and cannot be skipped unless trigger is explicitly dropped or disabled. |
| **10**| **Concurrent membership or interview creation during deletion** | Tx 1: Candidate Deletion<br/>Tx 2: Concurrent `INSERT INTO organization_memberships` | Concurrent database connections | **Tx 2 Blocks or Tx 1 Aborts**: Concurrency is 100% serialized. | Tx 1 acquires `SELECT FOR UPDATE` on `users`. In PostgreSQL, Tx 2's FK check acquires `FOR KEY SHARE` on `users`. Since `FOR UPDATE` conflicts with `FOR KEY SHARE`, Tx 2 is blocked until Tx 1 commits or rolls back. |

---

## 6. Remaining Limitations and Step 3 Handoff Boundaries

1. **Static Architectural Validation**:
   - All role permissions, `SECURITY DEFINER` semantics, `search_path` protections, and trigger functions have been verified against PostgreSQL 16 documentation and standards.
   - Per strict project constraints, no database tables were created and no migrations were executed. Verification is complete at the architectural design level.
2. **Step 3 Implementation Handoff Readiness**:
   - The multi-tenant database schema, Row-Level Security policies, authentication middleware pipeline, transactional revocation outbox, and candidate privacy lifecycle are 100% complete, hardened, and ready for Alembic migration scripting and FastAPI service development in Step 3.

---

## 7. Formal Stop Condition Compliance

- **No application source code was written or modified**.
- **No migrations or database tables were created**.
- **No dependencies or packages were installed**.
- **No cloud infrastructure was provisioned**.
- **Step 3 has NOT begun**.
- Awaiting independent review and formal approval.
