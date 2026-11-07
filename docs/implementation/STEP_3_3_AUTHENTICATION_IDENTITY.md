# Step 3.3 — Authentication & Identity Foundation Implementation

## 1. Executive Summary

This document records the architectural design, implementation details, and verification outcomes for **Step 3.3: Authentication & Identity Foundation** of the AI HR Intelligence Platform (VER 2.0), including all final security audit corrections.

All components adhere strictly to the approved canonical specifications in:
- `docs/architecture/04_multi_tenant_architecture.md`
- `docs/architecture/05_database_design.md`
- `docs/architecture/06_entity_relationships.md`
- `docs/architecture/07_authentication_authorization.md`
- `docs/architecture/08_user_roles_permissions.md`
- `docs/architecture/16_security_privacy_compliance.md`
- `docs/architecture/21_architecture_decisions.md`
- `docs/architecture/CANDIDATE_IDENTITY_AND_PRIVACY.md`
- `docs/architecture/DATABASE_SECURITY_INVENTORY.md`

Step 3.3 establishes enterprise identity, cryptographic session management, RFC 6238 multi-factor authentication (MFA), dual-token HttpOnly cookie architecture, and the complete 6-layer authorization pipeline with PostgreSQL Row-Level Security (RLS) tenant context binding.

---

## 2. Global Identity & Data Architecture

The platform separates platform-wide human identity from tenant-scoped enterprise roles and candidate data:

```
Platform Global:
  User (id: UUIDv7, email: citext, password_hash: Argon2id, token_version: int, ...)
    ├── CandidateUserProfile (user_id: FK, phone, headline, preferred_locations, ...)
    ├── UserSession (id: UUIDv7, user_id: FK, tenant_id: FK?, refresh_token_hash: str, ...)
    │     └── SessionTokenHistory (id: UUIDv7, session_id: FK (CASCADE), token_hash: str, created_at: TIMESTAMPTZ)
    └── AuthRevocationOutbox (id: UUIDv7, event_type: str, new_version: int, ...)

Tenant Scoped:
  Organization (id: UUIDv7, name: str, slug: citext, status: str, ...)
    ├── Role (id: UUIDv7, tenant_id: FK?, name: str, is_system: bool, ...)
    │     └── RolePermission ── Permission (code: citext, description: str)
    └── OrganizationMembership (id: UUIDv7, tenant_id: FK, user_id: FK, role_id: FK, role_version: int, ...)
```

### Key Security Invariants
1. **Zero Access to Recruitment Tables**: Auth workflows have zero access to candidate application tables, dossiers, screening scores, resumes, or interview notes.
2. **Global Users & Tenant Memberships**: A single `users` record represents a human being. Multi-tenant access is represented via `organization_memberships`. Candidates are represented globally with self-managed `candidate_user_profiles`.
3. **Transactional Outbox for Revocations**: High-impact security events (e.g., password changes, global logouts) insert an event into `auth_revocation_outbox` within the primary database transaction, incrementing `token_version` and setting `force_authoritative_check = TRUE`.
4. **Tenant-Role Integrity Enforced by Database Trigger**: Memberships cannot reference custom roles belonging to another tenant (`trg_enforce_membership_role_tenant` trigger).
5. **Cascading Token History Retention**: Historical refresh token hashes are tracked in `session_token_history` with foreign key `ON DELETE CASCADE` to `user_sessions.id`, ensuring zero orphaned security records upon session expiration or purge.

---

## 3. Cryptography & Authentication Implementation

### Password Hashing
- Implemented with **Argon2id** (`argon2-cffi`) using RFC 9106 recommended parameters:
  - Memory cost: 65,536 KiB (64 MiB)
  - Time cost: 3 iterations
  - Parallelism: 4 lanes
  - Automatic rehash detection (`hasher.check_needs_rehash(hash)`) on successful login.

### Multi-Factor Authentication (MFA) & Key Isolation
- **RFC 6238 TOTP**: 30-second step window, SHA-1 algorithm, 6 digits. Allows a ±1 step clock drift (±30 seconds) tolerance.
- **Dedicated Cryptographic Key Isolation**: Added `MFA_ENCRYPTION_KEY` in `Settings`, independent from `JWT_SECRET_KEY`. In production/staging, `MFA_ENCRYPTION_KEY` must be >= 32 characters and cannot equal `JWT_SECRET_KEY`.
- **AES-256-GCM Encryption at Rest**: TOTP secret keys are encrypted before storage in PostgreSQL using Authenticated Encryption with Associated Data (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`) with the dedicated MFA key.
- **Keyed HMAC-SHA256 Backup Codes**:
  - Hashed using HMAC-SHA256 with a dedicated server-side secret (`BACKUP_CODE_PEPPER`) and per-user message salt (`{user_id}:{clean_code}`).
  - `BACKUP_CODE_PEPPER` is validated in `Settings` at startup (minimum 32 characters, distinct from `JWT_SECRET_KEY` and `MFA_ENCRYPTION_KEY`). The secret is never stored in PostgreSQL.
  - Verification uses constant-time comparison (`hmac.compare_digest`).
  - Includes a fallback migration verification for existing unkeyed SHA-256 hashes to guarantee seamless backward compatibility.
- **Concurrency-Safe Single-Use Consumption**: Backup code redemption locks the `users` row with `with_for_update()`, removes the verified code, and commits before granting session access. Consumed codes cannot be reused in login or `disable_mfa`.
- **Replay Protection**: Verified TOTP codes are stored in Redis under `totp_replay:{user_id}:{code}` with a 90-second TTL to prevent replay attacks within the drift window.

### Token & Session Lifecycle
- **Access Tokens (JWT)**: Short-lived (15 minutes), signed with HMAC-SHA256 (`HS256`), containing:
  `sub`, `session_id`, `tenant_id`, `role`, `permissions`, `token_version`, `role_version`, `is_super_admin`, `exp`, `iat`, `iss`, `aud`.
- **Refresh Tokens**: Cryptographically random 48-byte high-entropy tokens, stored hashed (SHA-256) in `user_sessions`. Valid for 7 days with sliding expiration on refresh.
- **Persistent Full-Lifetime Refresh Token Reuse Detection**:
  - `refresh_session_tokens` serializes rotations using PostgreSQL row locks (`with_for_update()`).
  - Active session is located by `refresh_token_hash`. Upon rotation, the previous token hash is persisted into `session_token_history`.
  - If an incoming token does not match active session hashes, the service queries `session_token_history` (and fallback `previous_refresh_token_hash`).
  - Presenting any token previously rotated in the session's lifetime triggers `TOKEN_REUSE_DETECTED`, marks the entire session family `is_revoked = True`, evicts it from Redis, and logs a security violation.
- **Single-Session Logout**: `POST /auth/logout` extracts the authenticated session ID from the security context, revokes the specific PostgreSQL session row (`is_revoked = True`), deletes the session from Redis, and clears cookies.
- **Cookie Security**:
  - `aihr_access`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/`, 15-minute TTL.
  - `aihr_refresh`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/api/v1/auth`, 7-day TTL.
  - `aihr_csrf`: `HttpOnly=False` (JavaScript readable for double-submit header `X-CSRF-Token`), `SameSite=Lax`, `Path=/`.
- **Monotonic Version Fences & Role Eviction**:
  - Atomic Lua scripts (`SET_VERSION_FENCE_MONOTONIC_LUA`, `UPDATE_USER_TOKEN_VERSION_LUA`, and `UPDATE_ORG_ROLE_VERSION_LUA`).
  - `UPDATE_ORG_ROLE_VERSION_LUA` targets `session:{user_id}:*` via explicit user ID parameter, ensuring only sessions of the modified user are evicted while peer sessions remain untouched.
  - Absent fences fail closed (`TOKEN_VERSION_STALE` / `ROLE_VERSION_STALE`).

---

## 4. Multi-Tenant Authorization Pipeline

Implemented in `backend/app/modules/auth/dependencies.py` via FastAPI dependency injection:

### 6-Layer Request Validation Pipeline
```
[ Incoming Request ]
        │
        ▼
Layer 1: Cryptographic JWT Validation (Signature, Issuer, Audience, Expiry)
        │
        ▼
Layer 2: Server-Side Session & Exact Version Fence Check (Redis)
        ├─► State B: Cache Miss (Redis reachable, key absent) ──► STRICT REJECTION (401)
        │                                                          (Strict negative assertion: DB NOT queried)
        ├─► State A: Cache Hit ──► Check Version Invariants:
        │                          jwt.token_version == session.token_version == user_current_fence
        │                          jwt.role_version == session.role_version == org_current_fence
        │                          (Missing fence or mismatch ──► Evict session & raise 401)
        │
        ▼
Layer 3: Bounded Micro-Validation (>30s) or State C (Redis Outage) Fallback
        ├─► Authoritative Session Validation in PostgreSQL:
        │     1. user_sessions.id == token.session_id AND user_sessions.user_id == token.user_id
        │     2. NOT user_sessions.is_revoked (Rejects revoked sessions during Redis outage)
        │     3. user_sessions.expires_at >= NOW() (Rejects expired sessions)
        │     4. user_sessions.token_version == token.token_version
        │     5. users.is_active AND users.token_version == token.token_version
        │     6. organization_memberships.is_active AND role_version == token.role_version
        │     7. organizations.status == 'active'
        │
        ▼
Layer 4: Tenant Scope & RLS Context Binding
        ├─► Set PostgreSQL transaction-local setting:
        │   SELECT set_config('app.current_tenant_id', tenant_id, true);
        │   (Automatically cleared by PostgreSQL upon transaction commit/rollback)
        │
        ▼
Layer 5: Capability-Based Permission Verification
        ├─► require_permission("candidate:profile:manage")
        │   (Asserts required permission code is present in token payload)
        │
        ▼
Layer 6: Security Context Injection
        └─► Inject immutable SecurityContext(user_id, tenant_id, session_id, role, permissions, is_super_admin) into route handler
```

---

## 5. Database Schema & Alembic Migration

Domain migration created: `backend/alembic/versions/001_initial_auth_and_identity.py`

### Tables Created
- `organizations`: Tenant root entity with status, tier, settings.
- `users`: Platform-wide user entity with Argon2id hash, encrypted MFA secret, keyed backup codes, token version.
- `candidate_user_profiles`: Candidate profile details (phone, headline, preferred locations).
- `roles`: System and tenant-custom roles with `is_system` and `tenant_id`.
- `permissions`: Granular capability codes (e.g. `jobs:create`, `interviews:scorecard_submit`).
- `role_permissions`: Join table linking roles to capability permissions.
- `organization_memberships`: Tenant memberships linking users and roles.
- `user_sessions`: Active refresh sessions with IP, user-agent, `refresh_token_hash`, `token_version`, `is_revoked`.
- `session_token_history`: Persistent token reuse registry with `session_id` FK (CASCADE), `token_hash`, `created_at`.
- `auth_revocation_outbox`: Transactional event table for asynchronous cache synchronization.

### PostgreSQL Constraints & RLS
- **PostgreSQL Row-Level Security (RLS)**:
  - Enabled and enforced on `organization_memberships` via:
    ```sql
    ALTER TABLE organization_memberships ENABLE ROW LEVEL SECURITY;
    ALTER TABLE organization_memberships FORCE ROW LEVEL SECURITY;
    CREATE POLICY org_mem_tenant_restrict ON organization_memberships
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    ```
- **Tenant-Role Integrity Trigger**:
  - `fn_enforce_membership_role_tenant` and `trg_enforce_membership_role_tenant` ensure cross-tenant role assignment is rejected at the database level with `check_violation`.

---

## 6. Verification & Automated Test Suite

A comprehensive test suite of 85 security unit and integration tests:

1. **`backend/tests/test_auth_crypto.py`** (6 tests):
   - AES-256-GCM round-trip encryption/decryption of MFA secret keys with dedicated MFA key.
   - RFC 6238 TOTP code generation, verification, and clock drift tolerance.
   - `otpauth://` URI formatting for QR code generation.
   - Backup code generation, keyed HMAC-SHA256 hashing with `BACKUP_CODE_PEPPER` + user salt, and single-use matching.
   - Backward compatibility: migration verification of legacy unkeyed SHA-256 backup codes.
   - Secure token generation and CSRF token verification.

2. **`backend/tests/test_auth_jwt.py`** (5 tests):
   - JWT creation, decoding, and claims validation.
   - Tampered signature rejection (`401 Unauthorized`).
   - Expired token rejection.
   - Cookie security flags (`HttpOnly`, `Secure`, `SameSite`, `Path`).
   - Cookie clearing upon logout.

3. **`backend/tests/test_auth_mfa.py`** (4 tests):
   - Complete MFA enrollment and activation flow.
   - MFA login challenge response flow (`mfa_required` status to full token issuance).
   - Redis replay protection preventing reuse of a TOTP code within the drift window.
   - Backup code single-use consumption and prevention of reuse in disable-MFA.

4. **`backend/tests/test_auth_api.py`** (8 tests):
   - User registration with normalized email and password hashing.
   - Duplicate email registration conflict (`409 Conflict`).
   - Successful login setting HttpOnly cookies.
   - Generic authentication failure preventing username enumeration.
   - Suspended user rejection.
   - Redis login rate limiting (5 attempts per minute).
   - Refresh token rotation and reuse detection invalidating sessions (`TOKEN_REUSE_DETECTED`).
   - Single-session logout revoking database session and deleting Redis cache.

5. **`backend/tests/test_auth_authorization.py`** (8 tests):
   - Capability-based permission checks (`require_permission`).
   - Exact version fence rejection of stale tokens (`TOKEN_VERSION_STALE`).
   - State-B negative assertion: cache miss rejects with 401 without querying PostgreSQL.
   - Multi-tenant organization switching protocol with fresh claims and CSRF tokens.
   - Missing Redis version fence strictly rejected (fail closed).
   - Monotonic version fence cannot regress under concurrent race conditions.
   - Cross-tenant role assignment rejection during organization switch.
   - Targeted user session eviction via corrected Lua script leaving unrelated users untouched.

6. **`backend/tests/test_config.py`** (8 tests):
   - Rejection of default secrets in production.
   - Validation of `DATABASE_URL` and `DATABASE_SYNC_URL`.
   - Independent validation of `MFA_ENCRYPTION_KEY` preventing reuse of `JWT_SECRET_KEY`.
   - Independent validation of `BACKUP_CODE_PEPPER` (length >= 32 chars, distinct from JWT and MFA keys).

7. **`backend/tests/integration/test_postgres_lifecycle.py`** (11 tests):
   - PostgreSQL connection and session lifecycle.
   - Commit and rollback mechanics.
   - Transaction-local tenant context isolation (`is_local=True`).
   - Connection pool tenant context cleanup listener.
   - Alembic migration upgrade to head.
   - Concurrent refresh token rotation serialization and reuse detection.
   - Concurrent backup code redemption serialization preventing double-consumption.
   - Cross-tenant role assignment database trigger rejection.
   - State C Redis outage: authoritative `user_sessions` validation rejects revoked, expired, or version-mismatched sessions.
   - Multi-generation token rotation (A → B → C) and full-lifetime reuse detection of Token A with CASCADE history cleanup.

### Verification Summary
- **Python Compilation**: 0 errors (`compileall`).
- **Code Linter**: `ruff check` passed with 0 errors.
- **Code Formatter**: `ruff format --check` passed across 54 files.
- **Static Type Safety**: `mypy --config-file backend/pyproject.toml backend/app` passed with 0 errors across 36 source files.
- **Pytest Suite**: 74 passed, 11 skipped (container PostgreSQL integration tests skip locally without host DB, execute in GitHub Actions CI), 0 failures. Backend statement coverage: 81%.
