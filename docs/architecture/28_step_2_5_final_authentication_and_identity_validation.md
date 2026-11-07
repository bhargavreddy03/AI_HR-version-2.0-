# Step 2.5 — Final Authentication, Session Revocation, Vector Integrity and Identity Validation Report

## 1. Executive Summary & Design Scope

This validation report formalizes the architectural corrections executed under **Step 2.5 — Final Embedding, Session Revocation, and Global Identity Integrity**. 

Following independent review of `architecture(4).zip`, four critical structural and security invariants were identified and definitively resolved across the system architecture documentation:
1. **Embedding Model-to-Dimension Relational Integrity**: Enforced database-level guarantees ensuring stored vector dimensions strictly match the registered model specifications.
2. **Authoritative Redis Session Revocation Semantics**: Formulated the 3-state runtime decision matrix, strictly eliminating session resurrection vulnerabilities on cache misses.
3. **Comprehensive Global User Deletion Dependency Governance**: Cataloged every relational dependency referencing global user accounts, decoupling candidate Right-to-be-Forgotten erasure from corporate identity retention.
4. **Relational Table Count Canonicalization**: Reconciled all documentation to consistently identify **33 tenant-scoped tables** and **10 platform-global tables** (43 tables total).

### Strict Design-Only Rule Compliance:
- **No application source code was written or modified**.
- **No database migrations or tables were executed**.
- **No packages or dependencies were installed**.
- **No cloud infrastructure was provisioned**.
- **Step 3 has NOT begun**.
- All deliverables are maintained strictly as Markdown documents inside `docs/architecture/`.

---

## 2. Issue 1: Embedding Model-to-Dimension Integrity

### The Defect:
Previously, `candidate_document_embeddings` and `job_embeddings` maintained a single-column foreign key `REFERENCES embedding_models(model_identifier)`. This only proved that the model name existed; it did **not** prevent inserting a 768-dimension vector under a 1536-dimension model identifier, creating a critical vector similarity query failure in pgvector.

### Architectural Remediation:
1. Added `CONSTRAINT uq_embedding_models_dims UNIQUE (model_identifier, expected_dimensions)` to the `embedding_models` table.
2. Added composite foreign keys on `(model_identifier, vector_dimensions) REFERENCES embedding_models(model_identifier, expected_dimensions)` in both `candidate_document_embeddings` and `job_embeddings`.
3. Preserved the exactly-one-vector-column `CHECK` constraint ensuring that the populated vector column strictly corresponds to `vector_dimensions`.
4. Corrected PostgreSQL 16 partial HNSW index syntax (`WITH` parameters precede `WHERE` clause).
5. Documented the enforcement boundary: foreign keys cannot conditionally enforce `WHERE is_active = TRUE`. The application/worker layer acts as the primary gate blocking deactivated models, backed by an optional database `BEFORE INSERT` trigger.

### Valid PostgreSQL 16 DDL:

```sql
-- 1. Platform-Global Model Registry Table
CREATE TABLE embedding_models (
    model_identifier VARCHAR(100) PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    expected_dimensions INT NOT NULL CHECK (expected_dimensions IN (1536, 1024, 768)),
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Required composite unique key to support composite foreign key references
    CONSTRAINT uq_embedding_models_dims UNIQUE (model_identifier, expected_dimensions)
);

-- Seed approved model identifiers
INSERT INTO embedding_models (model_identifier, provider, expected_dimensions, is_active) VALUES
('text-embedding-3-small', 'openai', 1536, true),
('amazon.titan-embed-text-v1', 'aws_bedrock', 1536, true),
('cohere.embed-english-v3', 'aws_bedrock', 1024, true),
('bge-base-en-v1.5', 'huggingface', 768, true);

-- 2. Tenant-Scoped Candidate Document Embeddings Table
CREATE TABLE candidate_document_embeddings (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    document_id UUID NOT NULL,
    model_identifier VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    vector_dimensions INT NOT NULL,
    embedding_1536 vector(1536),
    embedding_1024 vector(1024),
    embedding_768 vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Composite Tenant-Safe Foreign Key
    CONSTRAINT fk_cand_emb_doc
        FOREIGN KEY (tenant_id, document_id)
        REFERENCES candidate_documents(tenant_id, id)
        ON DELETE CASCADE,

    -- Database-Enforced Model-to-Dimension Integrity Composite Foreign Key
    CONSTRAINT fk_cand_emb_model_dims
        FOREIGN KEY (model_identifier, vector_dimensions)
        REFERENCES embedding_models(model_identifier, expected_dimensions)
        ON DELETE RESTRICT,

    -- Unique constraint per document, model, and version
    CONSTRAINT uq_cand_emb_version
        UNIQUE (tenant_id, document_id, model_identifier, model_version),

    -- Exactly-one-vector-column CHECK constraint matching vector_dimensions
    CONSTRAINT chk_cand_emb_dimensions CHECK (
        (vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR
        (vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR
        (vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)
    )
);

-- Partial HNSW Indexes (PostgreSQL 16 Syntax: WITH precedes WHERE)
CREATE INDEX idx_cand_emb_1536 ON candidate_document_embeddings 
    USING hnsw (embedding_1536 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_1536 IS NOT NULL;

CREATE INDEX idx_cand_emb_1024 ON candidate_document_embeddings 
    USING hnsw (embedding_1024 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_1024 IS NOT NULL;

CREATE INDEX idx_cand_emb_768 ON candidate_document_embeddings 
    USING hnsw (embedding_768 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_768 IS NOT NULL;

-- 3. Tenant-Scoped Job Embeddings Table
CREATE TABLE job_embeddings (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    job_id UUID NOT NULL,
    model_identifier VARCHAR(100) NOT NULL,
    model_version VARCHAR(50) NOT NULL,
    vector_dimensions INT NOT NULL,
    embedding_1536 vector(1536),
    embedding_1024 vector(1024),
    embedding_768 vector(768),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Composite Tenant-Safe Foreign Key
    CONSTRAINT fk_job_emb_job
        FOREIGN KEY (tenant_id, job_id)
        REFERENCES jobs(tenant_id, id)
        ON DELETE CASCADE,

    -- Database-Enforced Model-to-Dimension Integrity Composite Foreign Key
    CONSTRAINT fk_job_emb_model_dims
        FOREIGN KEY (model_identifier, vector_dimensions)
        REFERENCES embedding_models(model_identifier, expected_dimensions)
        ON DELETE RESTRICT,

    -- Unique constraint per job, model, and version
    CONSTRAINT uq_job_emb_version
        UNIQUE (tenant_id, job_id, model_identifier, model_version),

    -- Exactly-one-vector-column CHECK constraint matching vector_dimensions
    CONSTRAINT chk_job_emb_dimensions CHECK (
        (vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR
        (vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR
        (vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)
    )
);

-- Partial HNSW Indexes
CREATE INDEX idx_job_emb_1536 ON job_embeddings 
    USING hnsw (embedding_1536 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_1536 IS NOT NULL;

CREATE INDEX idx_job_emb_1024 ON job_embeddings 
    USING hnsw (embedding_1024 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_1024 IS NOT NULL;

CREATE INDEX idx_job_emb_768 ON job_embeddings 
    USING hnsw (embedding_768 vector_cosine_ops)
    WITH (m = 16, ef_construction = 64)
    WHERE embedding_768 IS NOT NULL;
```

---

## 3. Issue 2: Redis Session Lookup & Revocation Semantics

### The Defect:
Previously, the validation flow stated that if a session lookup experienced a "cache miss", the system could fall back to PostgreSQL. In an active Redis cluster, session deletion is the authoritative mechanism for user logout and administrative revocation. Allowing a cache miss to query PostgreSQL risked resurrecting an evicted session if database write replication or status lag occurred.

### Architectural Remediation:
Formulated an unambiguous 3-state runtime decision matrix in `07_authentication_authorization.md`:

| Redis Runtime State | Key Presence | Middleware Evaluation | PostgreSQL Fallback Permitted? | Final Result | Security Rationale |
|:---|:---|:---|:---:|:---:|:---|
| **State A: Reachable & Key Found** | Key exists in Redis | Verify `session.token_version == jwt.token_version` AND `session.role_version == jwt.role_version` AND user active. | **NO** | `200 OK` (Proceed) | Fast-path affirmative cache hit. Authoritative session is verified active. |
| **State B: Reachable & Key Absent** | Key returns `nil` (Cache Miss) | **Strictly Revoked/Expired**. Immediately reject request and clear auth cookies. | **NO (FORBIDDEN)** | `401 Unauthorized` (`SESSION_REVOKED`) | An affirmative cache miss in a healthy Redis instance indicates logout, administrative eviction, or TTL expiry. Querying DB is forbidden to prevent resurrecting revoked sessions. |
| **State C1: Unreachable & DB Active** | Redis network timeout / connection error | Catch exception; execute controlled fallback query to PostgreSQL `sessions` + `users`. | **YES (Outage Only)** | `200 OK` (Proceed) | Degraded failover mode maintains enterprise uptime during transient Redis restarts while verifying durable database status. |
| **State C2: Unreachable & DB Inactive** | Redis down; DB returns `revoked_at IS NOT NULL` or `is_active = FALSE` | Reject request. | **YES (Outage Only)** | `401 Unauthorized` (`SESSION_REVOKED`) | Durable PostgreSQL audit confirms session was revoked prior to outage or user is disabled. |
| **State C3: Unreachable & DB Outage** | Both Redis and DB fail or time out ($>200\text{ ms}$) | **Fail Closed**. Terminate pipeline. | N/A | `503 Service Unavailable` (`AUTH_UNAVAILABLE`) | Fail-closed security posture guarantees unverified tokens are never accepted blindly. |

### Immediate Invalidation on Role and Permission Changes:
- `organization_memberships` maintains `role_version INT NOT NULL DEFAULT 1`.
- When an administrator modifies a user's role or permissions:
  1. The API synchronously increments `organization_memberships.role_version` in PostgreSQL.
  2. The API immediately updates the Redis session key with the new `role_version`.
  3. The next API request evaluates `jwt.role_version == session.role_version`.
  4. Any access token stamped with the prior `role_version` is rejected with `401 Unauthorized` (`ROLE_VERSION_MISMATCH`), triggering an instant silent refresh—**eliminating the 15-minute token staleness window**.

### Concurrent Operations & In-Flight Request Handling:
- **Concurrent Logout**: First request deletes the Redis key; concurrent requests hitting Redis receive State B (`nil` $\rightarrow$ `401 Unauthorized`).
- **Account Suspension**: Synchronously sets `users.is_active = FALSE` and executes Redis `DEL` across all user session keys.
- **Organization Suspension**: Synchronously sets `organizations.status = 'suspended'`, caught immediately at Layer 5 (`403 Forbidden`).
- **In-Flight Requests**: If a request has already passed Layer 2 and entered an active PostgreSQL transaction, the transaction commits under standard ACID isolation. All subsequent requests are blocked at Layer 2.

---

## 4. Issue 3: Global User Deletion Dependency Inventory

### The Defect:
Candidate Right-to-be-Forgotten workflows previously threatened to cascade-delete corporate user accounts, or claimed that a user could be hard-deleted as long as they had "no active memberships", ignoring historical interviewer scorecards, audit logs, and compliance records.

### Architectural Remediation:
1. Created a complete dependency inventory covering the **9 relational tables** with database foreign keys referencing `users(id)` and **2 application-level / policy dependencies**.
2. Decoupled **Candidate Profile Erasure** from **Global User Deletion**:
   - External candidates with zero corporate ties: Full candidate erasure + global user hard-delete.
   - Dual-role users (employees, recruiters, interviewers): Erases candidate profile, portfolio, and resumes, but **strictly preserves the `users` and `organization_memberships` rows**.
3. Reconciled deletion behaviors across all user dependencies:

| Dependent Entity | Referencing Column | FK Constraint | Hard-Delete Impact on `users` | Safe Deletion Pre-Condition & Architectural Policy | Real DB FK vs App Dependency |
|:---|:---|:---|:---|:---|:---:|
| **`candidate_user_profiles`** | `user_id` | `ON DELETE CASCADE` | Deleted automatically. | Pre-condition: Candidate initiates GDPR/DPDP erasure request. | **Real DB FK** |
| **`organization_memberships`** | `user_id` | `ON DELETE CASCADE` | Corporate memberships deleted. | **BLOCK IF COUNT > 0**: User must have zero active or inactive memberships. If memberships exist, corporate identity is retained. | **Real DB FK** |
| **`interview_scorecards`** | `interviewer_id` | **`ON DELETE RESTRICT`** | **DB Blocks Deletion!** | **STRICT BLOCK**: Statutory hiring compliance mandates retaining interviewer scorecards. `users` row cannot be hard-deleted; system executes Account Scrambling & Deactivation instead (`is_active = FALSE`). | **Real DB FK** |
| **`interview_participants`** | `user_id` | `ON DELETE CASCADE` | Attendance records deleted. | **BLOCK IF FUTURE INTERVIEWS EXIST**: User must be unassigned from all upcoming interview schedules (`scheduled_at >= NOW()`). | **Real DB FK** |
| **`jobs`** | `hiring_manager_id` | `ON DELETE SET NULL` | Set to `NULL`. | **BLOCK IF ACTIVE JOBS EXIST**: Open jobs assigned to the user must be reassigned prior to deletion. | **Real DB FK** |
| **`screening_runs`** | `created_by` | `ON DELETE SET NULL` | Set to `NULL`. | Permitted: Historical batch runs retain parameters and scores with `created_by = NULL`. | **Real DB FK** |
| **`comments`** | `author_id` | `ON DELETE SET NULL` | Set to `NULL`. | Permitted: Candidate notes preserved with author attributed to "Deleted User". | **Real DB FK** |
| **`candidate_profiles`** | `user_id` | `ON DELETE SET NULL` | Set to `NULL`. | Permitted: Employer candidate dossier anonymized in place under statutory retention. | **Real DB FK** |
| **`platform_audit_logs`** | `actor_id` | `ON DELETE SET NULL` | Set to `NULL`. | Permitted: Global administrative audit records remain immutable with `actor_id = NULL`. | **Real DB FK** |
| **`organizations`** | Admin role via membership | RBAC | N/A | **STRICT BLOCK**: User must not be the sole active administrator of any organization. Admin ownership must be transferred first. | **App Dependency** |
| **Legal Compliance** | Litigation Hold Flag | Policy | N/A | **STRICT BLOCK**: No active litigation hold or statutory legal retention period flagged against the user identity. | **App Dependency** |

---

## 5. Issue 4: Canonical Relational Table Counts

### The Defect:
`DATABASE_SECURITY_INVENTORY.md` contained an outdated heading indicating "9 Platform-Global Tables" with an appended correction note, leading to potential inconsistency across summaries.

### Architectural Remediation:
1. Reconciled all architecture documents (`DATABASE_SECURITY_INVENTORY.md`, `23_step_2_summary.md`, and validation reports) to canonical counts:
   - **Tenant-Scoped Tables**: Exactly **33 tables** (governed by PostgreSQL Restrictive RLS, permissive application policies, and composite tenant foreign keys).
   - **Platform-Global Tables**: Exactly **10 tables** (governed by application RBAC and global administrator policies, including the `embedding_models` registry).
   - **Total Relational Schema**: Exactly **43 tables**.
2. Removed contradictory historical notes.

---

## 6. Validation Checklist & Status Matrix

| Validation Criteria | Target Specification | Status | Verified Document |
|:---|:---|:---:|:---|
| **Composite Embedding Constraints** | `UNIQUE (model_identifier, expected_dimensions)` + Composite FKs in embedding tables | **PASS** | `05_database_design.md` |
| **Vector Dimension Check** | Inline `CHECK` ensuring only matching dimension column is populated | **PASS** | `05_database_design.md` |
| **PostgreSQL 16 HNSW Syntax** | Partial indexes structured with `WITH` before `WHERE` clause | **PASS** | `05_database_design.md` |
| **Model Inactive Boundary** | Documented application/worker gate + optional DB trigger boundary | **PASS** | `05_database_design.md` |
| **3-State Redis Decision Matrix** | Explicit distinction: Hit, Reachable Miss (Strict 401, No DB), Outage (Fallback) | **PASS** | `07_authentication_authorization.md` |
| **No DB Resurrection on Cache Miss** | Explicit architectural ban on querying PostgreSQL when Redis is healthy | **PASS** | `07_authentication_authorization.md` |
| **Immediate Role Invalidation** | `role_version` validation forces immediate re-auth on permission updates | **PASS** | `07_authentication_authorization.md` |
| **Concurrent Operations Analysis** | Defined behaviors for concurrent logout, suspension, and in-flight calls | **PASS** | `07_authentication_authorization.md` |
| **Complete User Dependency Inventory**| Audited 9 relational tables with FKs referencing `users(id)` and 2 app dependencies | **PASS** | `CANDIDATE_IDENTITY_AND_PRIVACY.md` |
| **Candidate / Corporate Decoupling** | Pure candidate erasure vs. dual-role user corporate identity preservation | **PASS** | `CANDIDATE_IDENTITY_AND_PRIVACY.md` |
| **Account Scrambling Fallback** | Deactivation/scrambling when `ON DELETE RESTRICT` scorecards prevent hard delete | **PASS** | `CANDIDATE_IDENTITY_AND_PRIVACY.md` |
| **Canonical Table Count** | Exactly 33 tenant-scoped + 10 platform-global (43 total) | **PASS** | `DATABASE_SECURITY_INVENTORY.md` |
| **Entity Relationship Diagrams** | Added `EMBEDDING_MODELS` and composite relationships to ERD | **PASS** | `06_entity_relationships.md` |

---

## 7. Remaining Limitations and Step 3 Handoff Boundaries

1. **Static Documentation Verification Boundary**:
   - All SQL DDL, constraints, Redis decision flows, and deletion workflows have been verified against the PostgreSQL 16 relational model and Redis architectural standards.
   - Per strict project constraints, no database tables were created and no migrations were executed. Verification is complete at the architectural design level.
2. **Step 3 Implementation Handoff Readiness**:
   - The relational database schema, tenant-safe foreign key constraints, Row-Level Security policies, authentication pipeline, and candidate privacy lifecycle are 100% defined, consistent, and ready for Alembic migration scripting and FastAPI service development in Step 3.

---

## 8. Formal Stop Condition Compliance

- **No application code was created**.
- **No migrations or database tables were generated**.
- **No dependencies or packages were installed**.
- **No cloud infrastructure was provisioned**.
- **Step 3 has NOT begun**.
- Awaiting independent review and formal approval.
