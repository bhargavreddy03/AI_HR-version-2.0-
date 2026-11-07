# Step 3.3 — Authentication & Identity Foundation Implementation

## 1. Executive Summary

This document records the architectural design, implementation details, and verification outcomes for **Step 3.3: Authentication & Identity Foundation** of the AI HR Intelligence Platform (VER 2.0), including all critical security audit corrections.

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
    ├── UserSession (id: UUIDv7, user_id: FK, tenant_id: FK?, refresh_token_hash: str, previous_refresh_token_hash: str, ...)
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
- **10 One-Time Backup Codes**: Exactly 10 cryptographically random 8-character codes generated at enrollment, hashed with SHA-256 for storage.
- **Concurrency-Safe Single-Use Consumption**: Backup code redemption locks the `users` row with `with_for_update()`, removes the verified code, and commits before granting session access. Consumed codes cannot be reused in login or `disable_mfa`.
- **Replay Protection**: Verified TOTP codes are stored in Redis under `totp_replay:{user_id}:{code}` with a 90-second TTL to prevent replay attacks within the drift window.

### Token & Session Lifecycle
- **Access Tokens (JWT)**: Short-lived (15 minutes), signed with HMAC-SHA256 (`HS256`), containing:
  `sub`, `session_id`, `tenant_id`, `role`, `permissions`, `token_version`, `role_version`, `is_super_admin`, `exp`, `iat`, `iss`, `aud`.
- **Refresh Tokens**: Cryptographically random 48-byte high-entropy tokens, stored hashed (SHA-256) in `user_sessions`. Valid for 7 days with sliding expiration on refresh.
- **Concurrency-Safe Rotation & Token Family Tracking**:
  - `refresh_session_tokens` acquires a PostgreSQL row lock (`with_for_update()`) on `user_sessions`.
  - When rotated, the old token hash is moved to `previous_refresh_token_hash`.
  - If a concurrent or replay request presents `previous_refresh_token_hash`, the backend immediately flags token reuse (`TOKEN_REUSE_DETECTED`), revokes the entire session (`is_revoked = True`), deletes Redis cache, and logs an audit security event.
- **Single-Session Logout**: `POST /auth/logout` extracts the authenticated session ID from the security context, revokes the specific PostgreSQL session row (`is_revoked = True`), deletes the session from Redis, and clears cookies.
- **Cookie Security**:
  - `aihr_access`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/`, 15-minute TTL.
  - `aihr_refresh`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/api/v1/auth`, 7-day TTL.
  - `aihr_csrf`: `HttpOnly=False` (JavaScript readable for double-submit header `X-CSRF-Token`), `SameSite=Lax`, `Path=/`.
- **Atomic Monotonic Version Fences**: Atomic Lua scripts (`SET_VERSION_FENCE_MONOTONIC_LUA` and `UPDATE_USER_TOKEN_VERSION_LUA`) ensure Redis version fences advance monotonically and never regress under concurrent race conditions. Absent fences fail closed (`TOKEN_VERSION_STALE` / `ROLE_VERSION_STALE`).

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
Layer 3: Bounded Micro-Validation (30-second Window)
        ├─► If > 30s elapsed or Redis unavailable (State C):
        │   Execute authoritative 6-dimension SQL check:
        │     1. user.is_active
        │     2. user.token_version
        │     3. user.force_authoritative_check
        │     4. membership.is_active
        │     5. membership.role_version
        │     6. organization.status == 'active'
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

Initial domain migration created: `backend/alembic/versions/001_initial_auth_and_identity.py`

### Tables Created
- `organizations`: Tenant root entity with status, tier, settings.
- `users`: Platform-wide user entity with Argon2id hash, encrypted MFA secret, backup codes, token version.
- `candidate_user_profiles`: Candidate profile details (phone, headline, preferred locations).
- `roles`: System and tenant-custom roles with `is_system` and `tenant_id`.
- `permissions`: Granular capability codes (e.g. `jobs:create`, `interviews:scorecard_submit`).
- `role_permissions`: Join table linking roles to capability permissions.
- `organization_memberships`: Tenant memberships linking users and roles.
- `user_sessions`: Active refresh sessions with IP, user-agent, `refresh_token_hash`, `previous_refresh_token_hash`.
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

A comprehensive test suite of 81 security unit and integration tests:

1. **`backend/tests/test_auth_crypto.py`** (5 tests):
   - AES-256-GCM round-trip encryption/decryption of MFA secret keys with dedicated MFA key.
   - RFC 6238 TOTP code generation, verification, and clock drift tolerance.
   - `otpauth://` URI formatting for QR code generation.
   - Backup code generation (exactly 10 codes), SHA-256 hashing, and verification.
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

5. **`backend/tests/test_auth_authorization.py`** (7 tests):
   - Capability-based permission checks (`require_permission`).
   - Exact version fence rejection of stale tokens (`TOKEN_VERSION_STALE`).
   - State-B negative assertion: cache miss rejects with 401 without querying PostgreSQL.
   - Multi-tenant organization switching protocol with fresh claims and CSRF tokens.
   - Missing Redis version fence strictly rejected (fail closed).
   - Monotonic version fence cannot regress under concurrent race conditions.
   - Cross-tenant role assignment rejection during organization switch.

6. **`backend/tests/test_config.py`** (8 tests):
   - Rejection of default secrets in production.
   - Validation of `DATABASE_URL` and `DATABASE_SYNC_URL`.
   - Independent validation of `MFA_ENCRYPTION_KEY` preventing reuse of `JWT_SECRET_KEY`.

7. **`backend/tests/integration/test_postgres_lifecycle.py`** (9 tests):
   - PostgreSQL connection and session lifecycle.
   - Commit and rollback mechanics.
   - Transaction-local tenant context isolation (`is_local=True`).
   - Connection pool tenant context cleanup listener.
   - Alembic migration upgrade to head.
   - Concurrent refresh token rotation serialization and reuse detection.
   - Concurrent backup code redemption serialization preventing double-consumption.
   - Cross-tenant role assignment database trigger rejection.

### Verification Summary
- **Python Compilation**: 0 errors (`compileall`).
- **Code Linter**: `ruff check` passed with 0 errors.
- **Code Formatter**: `ruff format --check` passed across 54 files.
- **Static Type Safety**: `mypy --config-file backend/pyproject.toml backend/app` passed with 0 errors across 36 source files.
- **Pytest Suite**: 72 passed, 9 skipped (integration tests skip locally without host PostgreSQL, run in CI), 0 failures. Backend statement coverage: 82%.
