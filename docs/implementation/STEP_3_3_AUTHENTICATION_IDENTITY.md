# Step 3.3 — Authentication & Identity Foundation Implementation

## 1. Executive Summary

This document records the architectural design, implementation details, and verification outcomes for **Step 3.3: Authentication & Identity Foundation** of the AI HR Intelligence Platform (VER 2.0).

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

---

## 3. Cryptography & Authentication Implementation

### Password Hashing
- Implemented with **Argon2id** (`argon2-cffi`) using RFC 9106 recommended parameters:
  - Memory cost: 65,536 KiB (64 MiB)
  - Time cost: 3 iterations
  - Parallelism: 4 lanes
  - Automatic rehash detection (`hasher.check_needs_rehash(hash)`) on successful login.

### Multi-Factor Authentication (MFA)
- **RFC 6238 TOTP**: 30-second step window, SHA-1 algorithm, 6 digits. Allows a ±1 step clock drift (±30 seconds) tolerance.
- **AES-256-GCM Encryption at Rest**: TOTP secret keys are encrypted before storage in PostgreSQL using Authenticated Encryption with Associated Data (`cryptography.hazmat.primitives.ciphers.aead.AESGCM`).
- **One-Time Backup Codes**: 10 cryptographically random 8-character codes generated at enrollment, hashed with SHA-256 for storage, and burned upon first use.
- **Replay Protection**: Verified TOTP codes are stored in Redis under `totp_replay:{user_id}:{code}` with a 90-second TTL to prevent replay attacks within the drift window.

### Token & Session Lifecycle
- **Access Tokens (JWT)**: Short-lived (15 minutes), signed with HMAC-SHA256 (`HS256`), containing:
  `sub`, `session_id`, `tenant_id`, `role`, `permissions`, `token_version`, `role_version`, `is_super_admin`, `exp`, `iat`, `iss`, `aud`.
- **Refresh Tokens**: Cryptographically random 48-byte high-entropy tokens, stored hashed (SHA-256) in `user_sessions`. Valid for 7 days with sliding expiration on refresh.
- **Refresh Token Reuse Detection**: If a previously consumed or revoked refresh token is presented, all active sessions for that user are immediately revoked, mitigating token theft.
- **Cookie Security**:
  - `aihr_access`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/`, 15-minute TTL.
  - `aihr_refresh`: `HttpOnly=True`, `Secure=True` (prod/staging), `SameSite=Lax`, `Path=/api/v1/auth`, 7-day TTL.
  - `aihr_csrf`: `HttpOnly=False` (JavaScript readable for double-submit header `X-CSRF-Token`), `SameSite=Lax`, `Path=/`.
- **Atomic Global Logout**: Monotonic Lua script (`UPDATE_USER_TOKEN_VERSION_LUA`) atomically verifies and increments Redis version fences, evicting all cached user sessions across all devices.

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
        │                          (Mismatch ──► Evict session & raise 401)
        │
        ▼
Layer 3: Bounded Micro-Validation (30-second Window)
        ├─► If > 30s elapsed or Redis unavailable (State C):
        │   Execute authoritative 6-dimension SQL check:
        │     1. user.is_active
        │     2. user.token_version
        │     3. membership.is_active
        │     4. membership existence
        │     5. membership.role_version
        │     6. organization.status == 'active'
        │   Invalidation Barrier: If force_authoritative_check == True ──► Force cache eviction
        │
        ▼
Layer 4: Tenant & Membership Status Enforcement
        │
        ▼
Layer 5: PostgreSQL Row-Level Security (RLS) Context Binding
        ├─► Execute: SELECT set_config('app.current_tenant_id', :tenant_id, true)
        │   (Transaction-local, strictly prevents cross-tenant connection pool leakage)
        │
        ▼
Layer 6: Double-Submit CSRF Verification (POST, PUT, PATCH, DELETE)
        ├─► Constant-time comparison between cookie 'aihr_csrf' and header 'X-CSRF-Token'
        │
        ▼
[ SecurityContext Injected to Endpoint Handler ]
```

### Role & Capability Enforcement
- `require_authenticated_user`: Verifies authentication and returns `SecurityContext`.
- `require_active_tenant`: Ensures the user is operating within an active tenant context.
- `require_permission(code)`: Validates that `code` is present in the resolved capabilities (or caller is super admin).
- `require_role(allowed_roles)`: Validates role hierarchy.

### Organization Context Switching
- Implemented adhering to Architecture Document 07 Section 7:
  1. Validates target organization exists and is in `active` status.
  2. Confirms caller holds an active `organization_memberships` record in target tenant.
  3. Updates session active tenant ID and loads target tenant role capabilities.
  4. Issues fresh access token and CSRF tokens with updated claims.

---

## 5. Database Schema & Alembic Migration

The initial migration `backend/alembic/versions/001_initial_auth_and_identity.py` defines the foundational schema:

- **Tables Created**:
  - `users`: Core identity, password hash, MFA configuration, version fences, and invalidation barriers.
  - `candidate_user_profiles`: Candidate global attributes (phone, headline, location, links).
  - `organizations`: Tenant entities, status, slug, domain restrictions.
  - `roles`: Tenant-scoped and system roles (`candidate`, `recruiter`, `hiring_manager`, `org_admin`, `platform_super_admin`).
  - `permissions`: Capability codes (`jobs:create`, `candidates:read`, etc.).
  - `role_permissions`: Association table with composite primary key.
  - `organization_memberships`: Scoped tenant memberships with `role_version` and status.
  - `user_sessions`: Active refresh sessions with IP, user-agent, and expiration timestamps.
  - `auth_revocation_outbox`: Transactional event table for asynchronous cache synchronization.

- **PostgreSQL Row-Level Security (RLS)**:
  - Enabled and enforced on `organization_memberships` via:
    ```sql
    ALTER TABLE organization_memberships ENABLE ROW LEVEL SECURITY;
    ALTER TABLE organization_memberships FORCE ROW LEVEL SECURITY;
    CREATE POLICY org_mem_tenant_restrict ON organization_memberships
        FOR ALL
        USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
    ```

---

## 6. Verification & Automated Test Suite

A comprehensive test suite of 28 security unit and integration tests was implemented:

1. **`backend/tests/test_auth_crypto.py`** (5 tests):
   - AES-256-GCM round-trip encryption/decryption of MFA secret keys.
   - RFC 6238 TOTP code generation, verification, and clock drift tolerance.
   - `otpauth://` URI formatting for QR code generation.
   - Backup code generation, SHA-256 hashing, and verification.
   - Secure token generation and CSRF token verification.

2. **`backend/tests/test_auth_jwt.py`** (5 tests):
   - JWT creation, decoding, and claims validation.
   - Tampered signature rejection (`401 Unauthorized`).
   - Expired token rejection.
   - Cookie security flags (`HttpOnly`, `Secure`, `SameSite`, `Path`).
   - Cookie clearing upon logout.

3. **`backend/tests/test_auth_mfa.py`** (3 tests):
   - Complete MFA enrollment and activation flow.
   - MFA login challenge response flow (`mfa_required` status to full token issuance).
   - Redis replay protection preventing reuse of a TOTP code within the drift window.

4. **`backend/tests/test_auth_api.py`** (8 tests):
   - User registration with normalized email and password hashing.
   - Duplicate email registration conflict (`409 Conflict`).
   - Successful login setting HttpOnly cookies.
   - Generic authentication failure preventing username enumeration.
   - Suspended user rejection.
   - Redis login rate limiting (5 attempts per minute).
   - Refresh token rotation and reuse detection invalidating sessions.
   - Single-session and global logout revocation.

5. **`backend/tests/test_auth_authorization.py`** (4 tests):
   - Capability-based permission checks (`require_permission`).
   - Exact version fence rejection of stale tokens (`TOKEN_VERSION_STALE`).
   - State-B negative assertion: cache miss rejects with 401 without querying PostgreSQL.
   - Multi-tenant organization switching protocol with fresh claims and CSRF tokens.

### Verification Summary
- **Python Compilation**: 0 errors (`compileall`).
- **Code Linter**: `ruff check` passed with 0 errors.
- **Code Formatter**: `ruff format --check` passed across 54 files.
- **Static Type Safety**: `mypy --config-file backend/pyproject.toml backend/app` passed with 0 errors across 36 source files.
- **Pytest Suite**: 68 passed, 6 skipped (PostgreSQL/Redis live integration tests), 0 failures.
