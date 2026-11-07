# Consolidated Database Security, RLS & Constraint Inventory

This document provides a comprehensive inventory of every tenant-scoped table and platform-global table in the relational database, detailing composite tenant-safe foreign keys, deletion semantics, RLS policy directives, and required integration tests.

---

## 1. Master Tenant-Scoped Tables Security Matrix (33 Tables Total)

| # | Table Name | Tenant Key | Primary & Unique Keys | Composite Tenant-Safe Foreign Keys | RLS Directives | Permissive Policy Name | Restrictive Tenant Policy Name | Deletion Semantics | Required Multi-Tenant Integration Tests |
|:---:|:---|:---:|:---|:---|:---:|:---|:---|:---|:---|
| 1 | `organization_memberships` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, user_id)` | FK: `users(id)` ON DEL CASCADE<br/>FK: `departments(tenant_id, id)` ON DEL SET NULL (`department_id`) | ENABLE & FORCE RLS | `org_mem_app_user_perm` | `org_mem_tenant_restrict` | Cascade on user delete strictly blocked by RLS-aware trigger guard (`BYPASSRLS`); set null on department delete. | Verify user cannot query memberships in another tenant. |
| 2 | `departments` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `organizations(id)` ON DEL CASCADE | ENABLE & FORCE RLS | `departments_app_user_perm` | `departments_tenant_restrict` | Cascade on org delete; Restrict if active jobs exist. | Verify cross-tenant department lookup returns 404. |
| 3 | `teams` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `departments(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `teams_app_user_perm` | `teams_tenant_restrict` | Cascade on department delete. | Verify cross-tenant team isolation. |
| 4 | `invitations` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, email)` | FK: `organizations(id)` ON DEL CASCADE<br/>FK: `roles(id)` | ENABLE & FORCE RLS | `invitations_app_user_perm` | `invitations_tenant_restrict` | Cascade on org delete. | Verify cross-tenant invitation token hijacking fails. |
| 5 | `candidate_profiles` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `users(id)` ON DEL SET NULL | ENABLE & FORCE RLS | `cand_prof_app_user_perm` | `cand_prof_tenant_restrict` | Restrict if active applications exist; anonymize in place for GDPR. | Verify Tenant B cannot search Tenant A candidates. |
| 6 | `candidate_documents` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, checksum_sha256)` | FK: `candidate_profiles(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `cand_docs_app_user_perm` | `cand_docs_tenant_restrict` | Cascade on candidate profile hard delete; S3 file purged via Celery. | Verify S3 download presigned URL rejected for other tenant. |
| 7 | `candidate_skills` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, candidate_id, canonical_name)` | FK: `candidate_profiles(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `cand_skills_app_user_perm` | `cand_skills_tenant_restrict` | Cascade on candidate profile delete. | Verify skill queries filtered strictly by tenant. |
| 8 | `resume_versions` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, candidate_id, version_number)` | FK: `candidate_profiles(tenant_id, id)` ON DEL CASCADE<br/>FK: `candidate_documents(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `resume_ver_app_user_perm` | `resume_ver_tenant_restrict` | Cascade on candidate profile or document delete. | Verify version history scoped to tenant. |
| 9 | `job_requisitions` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `departments(tenant_id, id)` ON DEL SET NULL (`department_id`) | ENABLE & FORCE RLS | `job_req_app_user_perm` | `job_req_tenant_restrict` | Restrict on delete if published jobs exist. | Verify requisition budget data isolated to tenant. |
| 10 | `jobs` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, slug)` | FK: `departments(tenant_id, id)` ON DEL SET NULL (`department_id`)<br/>FK: `users(id)` ON DEL SET NULL (`hiring_manager_id`) | ENABLE & FORCE RLS | `jobs_app_user_perm` | `jobs_tenant_restrict` | Restrict on delete if applications exist; user delete blocked by trigger guard (`BYPASSRLS`) if active jobs assigned; set null if archived. | Verify hiring manager scoping: cannot view other departments' jobs. |
| 11 | `job_requirements` | `tenant_id` | PK: `id` | FK: `jobs(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `job_reqs_app_user_perm` | `job_reqs_tenant_restrict` | Cascade on job delete. | Verify requirement definitions cannot leak across tenants. |
| 12 | `job_skills` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, job_id, skill_name)` | FK: `jobs(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `job_skills_app_user_perm` | `job_skills_tenant_restrict` | Cascade on job delete. | Verify job skill weights isolated. |
| 13 | `applications` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, job_id, candidate_id)` | FK: `jobs(tenant_id, id)` ON DEL RESTRICT<br/>FK: `candidate_profiles(tenant_id, id)` ON DEL RESTRICT<br/>FK: `candidate_documents(tenant_id, id)` ON DEL SET NULL (`resume_document_id`)<br/>FK: `pipeline_stages(tenant_id, id)` ON DEL RESTRICT | ENABLE & FORCE RLS | `apps_app_user_perm` | `apps_tenant_restrict` | Restrict on job/candidate profile delete; nullify resume document on document purge. | Verify Tenant B cannot query or transition Tenant A application. |
| 14 | `application_status_history` | `tenant_id` | PK: `id` | FK: `applications(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `app_stat_hist_app_user_perm` | `app_stat_hist_tenant_restrict` | Cascade on application delete. | Verify audit history cannot leak across tenants. |
| 15 | `application_stage_history` | `tenant_id` | PK: `id` | FK: `applications(tenant_id, id)` ON DEL CASCADE<br/>FK: `pipeline_stages(tenant_id, id)` ON DEL RESTRICT | ENABLE & FORCE RLS | `app_stage_hist_app_user_perm` | `app_stage_hist_tenant_restrict` | Cascade on application delete; Restrict stage delete. | Verify transition timeline scoped to tenant. |
| 16 | `pipeline_templates` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `organizations(id)` ON DEL CASCADE | ENABLE & FORCE RLS | `pipe_temp_app_user_perm` | `pipe_temp_tenant_restrict` | Cascade on org delete; Restrict if active jobs use template. | Verify custom pipeline workflows isolated. |
| 17 | `pipeline_stages` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, template_id, stage_order)` | FK: `pipeline_templates(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `pipe_stages_app_user_perm` | `pipe_stages_tenant_restrict` | Cascade on template delete; Restrict if applications reside in stage. | Verify stage re-ordering is tenant-isolated. |
| 18 | `stage_transitions` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, from_stage_id, to_stage_id)` | FK: `pipeline_stages(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `stage_trans_app_user_perm` | `stage_trans_tenant_restrict` | Cascade on stage delete. | Verify FSM rules cannot be modified across tenants. |
| 19 | `screening_runs` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `jobs(tenant_id, id)` ON DEL CASCADE<br/>FK: `users(id)` ON DEL SET NULL | ENABLE & FORCE RLS | `screen_runs_app_user_perm` | `screen_runs_tenant_restrict` | Cascade on job delete. | Verify batch matching trigger isolated to tenant. |
| 20 | `screening_results` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, screening_run_id, application_id)` | FK: `screening_runs(tenant_id, id)` ON DEL CASCADE<br/>FK: `applications(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `screen_res_app_user_perm` | `screen_res_tenant_restrict` | Cascade on run or application delete. | Verify match scores & evidence quotes isolated to tenant. |
| 21 | `screening_score_components` | `tenant_id` | PK: `id` | **Composite FK**: `screening_results(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `screen_comp_app_user_perm` | `screen_comp_tenant_restrict` | Cascade on screening result delete. | Verify sub-score breakdown isolated. |
| 22 | `candidate_document_embeddings` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, document_id, model_identifier, model_version)` | **Composite FK**: `candidate_documents(tenant_id, id)` ON DEL CASCADE<br/>**Composite FK**: `embedding_models(model_identifier, expected_dimensions)` ON DEL RESTRICT | ENABLE & FORCE RLS | `cand_emb_app_user_perm` | `cand_emb_tenant_restrict` | Cascade on document delete; enforces `CHECK (chk_cand_emb_dimensions)`. | Verify HNSW vector similarity search never returns other tenant vectors. |
| 23 | `job_embeddings` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, job_id, model_identifier, model_version)` | **Composite FK**: `jobs(tenant_id, id)` ON DEL CASCADE<br/>**Composite FK**: `embedding_models(model_identifier, expected_dimensions)` ON DEL RESTRICT | ENABLE & FORCE RLS | `job_emb_app_user_perm` | `job_emb_tenant_restrict` | Cascade on job delete; enforces `CHECK (chk_job_emb_dimensions)`. | Verify job vector searches isolated. |
| 24 | `interview_rounds` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `jobs(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `int_rounds_app_user_perm` | `int_rounds_tenant_restrict` | Cascade on job delete. | Verify interview round definitions isolated. |
| 25 | `interview_schedules` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `applications(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `int_sched_app_user_perm` | `int_sched_tenant_restrict` | Protected by trigger guard `trg_interview_schedules_check_participants_active` on `status` and `scheduled_at` to prevent activating upcoming interviews with inactive/deleting participants; cascade on application delete. | Verify interview calendar slots cannot be read by other tenants. |
| 26 | `interview_participants` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, interview_id, user_id)` | FK: `interview_schedules(tenant_id, id)` ON DEL CASCADE<br/>FK: `users(id)` ON DEL CASCADE | ENABLE & FORCE RLS | `int_part_app_user_perm` | `int_part_tenant_restrict` | User delete blocked by trigger guard (`BYPASSRLS`) if upcoming interviews scheduled; historical participation cascades; cascades on interview schedule delete. | Verify panel participant list isolated. |
| 27 | `interview_scorecards` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)`<br/>UK: `(tenant_id, interview_id, interviewer_id)` | FK: `interview_schedules(tenant_id, id)` ON DEL CASCADE<br/>FK: `users(id)` ON DEL RESTRICT | ENABLE & FORCE RLS | `int_score_app_user_perm` | `int_score_tenant_restrict` | Strictly restricted by relational engine (ON DELETE RESTRICT) on user delete; cascade on interview schedule delete. | Verify private interviewer feedback is never exposed to candidate or other tenants. |
| 28 | `interview_feedback` | `tenant_id` | PK: `id` | **Composite FK**: `interview_scorecards(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `int_fb_app_user_perm` | `int_fb_tenant_restrict` | Cascade on scorecard delete. | Verify scorecard notes isolated. |
| 29 | `assessments` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `applications(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `assess_app_user_perm` | `assess_tenant_restrict` | Cascade on application delete. | Verify candidate assessments isolated. |
| 30 | `assessment_questions` | `tenant_id` | PK: `id`<br/>UK: `(tenant_id, id)` | FK: `assessments(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `assess_q_app_user_perm` | `assess_q_tenant_restrict` | Cascade on assessment delete. | Verify generated questions isolated. |
| 31 | `assessment_responses` | `tenant_id` | PK: `id` | **Composite FK**: `assessment_questions(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `assess_resp_app_user_perm` | `assess_resp_tenant_restrict` | Cascade on question delete. | Verify candidate answers isolated. |
| 32 | `comments` | `tenant_id` | PK: `id` | FK: `applications(tenant_id, id)` ON DEL CASCADE<br/>FK: `users(id)` ON DEL SET NULL | ENABLE & FORCE RLS | `comments_app_user_perm` | `comments_tenant_restrict` | Cascade on application delete. | Verify recruiter internal discussion timeline strictly isolated. |
| 33 | `activity_logs` | `tenant_id` | PK: `id` | FK: `applications(tenant_id, id)` ON DEL CASCADE | ENABLE & FORCE RLS | `act_logs_app_user_perm` | `act_logs_tenant_restrict` | Cascade on application delete. | Verify candidate timeline events isolated. |

---

## 2. Platform-Global Tables (Exactly 10 Tables Total)

The following **10 tables** are platform-global and governed strictly by application-level authorization (`is_super_admin` or user self-ownership):

1. `organizations` (Tenant root entity)
2. `users` (Global user identity, auth credentials, token_version, force_authoritative_check)
3. `candidate_user_profiles` (Candidate-owned personal profile & portfolio)
4. `roles` (System role definitions where `tenant_id IS NULL`)
5. `permissions` (Global capability codes)
6. `role_permissions` (Global permission mappings)
7. `subscription_plans` (SaaS commercial plan tiers)
8. `subscriptions` (Tenant subscription status & billing limits)
9. `platform_audit_logs` (Global administrative audit trail)
10. `embedding_models` (Model registry validating provider, dimensions, and active status)

---

## 3. Relational Table Count Summary

- **Tenant-Scoped Tables**: Exactly **33 tables** (governed by PostgreSQL Restrictive RLS + permissive user policies + composite tenant foreign keys).
- **Platform-Global Tables**: Exactly **10 tables** (governed by application-level RBAC and global administrator policies).
- **Total Relational Schema**: Exactly **43 tables** (supplemented by transactional infrastructure table `auth_revocation_outbox` for asynchronous Redis cache synchronization).

---

## 4. Master Relational Dependency Inventory for `users(id)`

Across the entire relational database, exactly **9 core business relational tables** (plus transactional infrastructure table `auth_revocation_outbox` with `ON DELETE RESTRICT`) enforce foreign key constraints pointing to the platform-global `users(id)` table:

1. `candidate_user_profiles.user_id` (Platform-Global Table 3) $\rightarrow$ `ON DELETE CASCADE` (Allowed CASCADE on candidate erasure)
2. `organization_memberships.user_id` (Tenant-Scoped Table 1) $\rightarrow$ `ON DELETE CASCADE` (**Strictly Rejected by DB Trigger Guard `fn_protect_user_cascade_deletion` with cross-tenant `BYPASSRLS`** if count > 0)
3. `candidate_profiles.user_id` (Tenant-Scoped Table 5) $\rightarrow$ `ON DELETE SET NULL` (Deliberate SET NULL; dossier anonymized under statutory retention)
4. `jobs.hiring_manager_id` (Tenant-Scoped Table 10) $\rightarrow$ `ON DELETE SET NULL` (**Strictly Rejected by DB Trigger Guard with `BYPASSRLS`** if assigned to active jobs; SET NULL allowed if archived)
5. `screening_runs.created_by` (Tenant-Scoped Table 19) $\rightarrow$ `ON DELETE SET NULL` (Deliberate SET NULL; batch run audit retained)
6. `interview_participants.user_id` (Tenant-Scoped Table 26) $\rightarrow$ `ON DELETE CASCADE` (**Strictly Rejected by DB Trigger Guard with `BYPASSRLS`** if assigned to upcoming scheduled interviews; historical participation allowed to cascade)
7. `interview_scorecards.interviewer_id` (Tenant-Scoped Table 27) $\rightarrow$ **`ON DELETE RESTRICT`** (**Strictly Rejected by PostgreSQL Relational Engine `ON DELETE RESTRICT`**; requires Account Scrambling & Deactivation)
8. `comments.author_id` (Tenant-Scoped Table 32) $\rightarrow$ `ON DELETE SET NULL` (Deliberate SET NULL; notes preserved with author attributed to "Former Employee")
9. `platform_audit_logs.actor_id` (Platform-Global Table 9) $\rightarrow$ `ON DELETE SET NULL` (Deliberate SET NULL; immutable audit log preserved)
10. `auth_revocation_outbox.user_id` (Transactional Infrastructure Table) $\rightarrow$ **`ON DELETE RESTRICT`** (**Strictly Rejected by PostgreSQL Relational Engine `ON DELETE RESTRICT`** and DB Trigger Guard `fn_protect_user_cascade_deletion`; pending invalidation events must complete Redis acknowledgement before deletion; table-level trigger `fn_prevent_delete_pending_outbox` strictly forbids deleting pending events)

**Application-Level & Policy Dependencies (Non-Table)**:
11. `organizations` Sole Administrator Check (RBAC Application Gate)
12. Statutory Litigation Hold Check (`users.litigation_hold == TRUE` Compliance Gate)

---

## 5. Master Security Roles and Least-Privilege Execution Model

To eliminate privilege escalation risks while enabling cross-tenant triggers and asynchronous cache propagation:

| Role Name | Type | Privileges & Grants | Purpose & Invariants |
| :--- | :--- | :--- | :--- |
| **`aihr_app_user`** | Connection Role (`LOGIN`) | Standard DML on tenant tables (subject to RLS); `EXECUTE` on public functions. Cannot bypass RLS. | Standard FastAPI backend connection pool role. Operates strictly within bound `app.current_tenant_id`. |
| **`aihr_deletion_guard_role`** | Definer Role (`NOLOGIN`, `BYPASSRLS`) | Strictly read-only (`SELECT` only) on `users`, `organization_memberships`, `jobs`, `interview_participants`, `interview_schedules`, `interview_scorecards`, and `auth_revocation_outbox`. **ZERO write grants**. | Owns `fn_protect_user_cascade_deletion()`, `fn_protect_organization_deletion()`, and child-table activation guards. Can inspect across RLS boundaries without any ability to modify data. |
| **`aihr_revocation_processor_role`** | Definer Role (`NOLOGIN`, `BYPASSRLS`) | Column-level least privilege: `SELECT, UPDATE (processed_at)` on `auth_revocation_outbox`; `SELECT (id, force_authoritative_check, is_active), UPDATE (force_authoritative_check, updated_at)` on `users`; `SELECT (id, tenant_id, user_id, is_active)` on `organization_memberships`; `SELECT (id), UPDATE (name)` on `organizations` (narrowest column-level grant on existing non-key `name` column for Level 0 `FOR UPDATE` locking). **ZERO recruitment table grants and ZERO candidate PII access**. | Owns `fn_process_auth_revocation_event()`. Safely clears user barrier flags across tenants without access to sensitive hiring or personal candidate data. |

---

## 6. Master Global Lock Hierarchy & Concurrency Protocol

To mathematically eliminate deadlocks between parent entity mutations/deletions and asynchronous child table workers, all transactions across the platform acquire row-level locks strictly in the following monotonic order:

$$\text{Level 0: } \texttt{organizations(id ASC)} \quad \longrightarrow \quad \text{Level 1: } \texttt{users(id ASC)} \quad \longrightarrow \quad \text{Level 2: } \texttt{jobs(id ASC)} \quad \longrightarrow \quad \text{Level 3: } \texttt{interview\_schedules(id ASC)} \quad \longrightarrow \quad \text{Level 4: } \texttt{interview\_participants(id ASC)} \quad \longrightarrow \quad \text{Level 5: } \texttt{auth\_revocation\_outbox(id ASC)}$$

1. **Top-Down Acquisition Rule**: No transaction may acquire a lock on an entity at Level $N$ if it holds a lock on an entity at Level $M$ where $M > N$.
2. **Reversed Outbox Locking & Phantom Prevention**: `fn_process_auth_revocation_event` reads outbox metadata via non-locking snapshot, acquires Level 0 (`organizations` FOR UPDATE — which blocks concurrent membership insertions via foreign-key `FOR KEY SHARE` engine conflict, blocks concurrent membership mutations via Level 0 protocol, and serializes against organization deletions), and acquires Level 1 (`users` individually in deterministic ascending UUID order without aggregates, capturing the exact set into `v_locked_users`) **FIRST**, and locks Level 5 (`auth_revocation_outbox`) **SECOND**.
3. **Deadlock Immunity**: Parent deletions (`DELETE FROM users`, `DELETE FROM organizations`) and outbox processing follow the exact same direction, eliminating cycles in the wait-for graph. Concurrent collisions safely serialize under `ON DELETE RESTRICT`.
