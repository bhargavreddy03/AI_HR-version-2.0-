# Step 3.4 — Production-Grade Database Foundation (PostgreSQL 16 + SQLAlchemy 2.x + Alembic + pgvector)

## 1. Executive Summary & Objective

Step 3.4 establishes the enterprise relational database and neural vector storage foundation for the AI-Powered Recruitment & HR Intelligence Platform. Built strictly upon the approved Step 2 architecture specifications (`05_database_design.md`, `04_multi_tenant_architecture.md`, `12_ai_architecture.md`, and `DATABASE_SECURITY_INVENTORY.md`), this milestone integrates:

1. **PostgreSQL 16 & SQLAlchemy 2.x Asynchronous Layer**: Clean asynchronous modular architecture under `backend/app/db/` using `asyncpg` with explicit transaction management, pool safety lifecycle listeners, and application-instance resource isolation.
2. **PostgreSQL Row-Level Security (RLS) Multi-Tenancy**: Zero-trust shared-schema isolation enforcing `ENABLE ROW LEVEL SECURITY` and `FORCE ROW LEVEL SECURITY`, transaction-local context (`set_config('app.current_tenant_id', :tenant_id, true)`), and connection checkin pool reset hooks to eliminate cross-tenant leakage.
3. **Alembic Migration Pipeline**: Deterministic, asynchronous, and reversible schema migration infrastructure preserving existing migration history and introducing revision `002_db_foundation_pgvector`.
4. **pgvector Integration & Model-to-Dimension Integrity**: Extension activation, database-enforced model registry (`embedding_models` Table 10), and dimension-safe vector storage tables (`candidate_document_embeddings` Table 22 and `job_embeddings` Table 23) with composite foreign keys, dimension check constraints, and partial HNSW cosine vector indexes (`m = 16, ef_construction = 64`).

---

## 2. Relational Database & ORM Architecture

### 2.1 Package Organization (`backend/app/db/`)
The database foundation is structured into dedicated, decoupled components:
- `backend/app/db/base.py`: Central declarative `Base` (`AsyncAttrs`, `DeclarativeBase`), naming conventions (`POSTGRES_NAMING_CONVENTION`), common mixins (`TimestampMixin`, `TenantScopedMixin`), and model registration.
- `backend/app/db/session.py`: Asynchronous engine creation (`create_db_engine`), session factory (`create_session_factory`), singleton getters (`get_engine`, `get_session_factory`), FastAPI dependency (`get_db`), transaction context manager (`transactional_session`), and health probe (`check_database_health`).
- `backend/app/db/events.py`: Connection pool event listeners (`register_pool_cleanup_listener`) providing defense-in-depth parameter resets on checkin and invalidation on failure.
- `backend/app/db/__init__.py`: Clean public API for the database layer.
- `backend/app/core/base.py` & `backend/app/core/database.py`: Fully backward-compatible re-exports preserving existing Step 3.1–3.3 module contracts and test patch targets.

### 2.2 Primary Key Convention: Application-Generated UUIDv7
- RFC 9562-compliant, time-ordered 128-bit UUIDv7 identifiers are generated at the application layer via `generate_uuid7()` (`app.db.base`).
- Eliminates database sequence contention, ensures monotonic index locality, and enables client-side UUID generation before transaction commit.
- Stored as native PostgreSQL `UUID` (`PG_UUID(as_uuid=True)`).

### 2.3 Timezone-Aware Timestamps (`TIMESTAMPTZ`)
- Timestamp columns (`created_at`, `updated_at`) strictly use `TIMESTAMP(timezone=True)`.
- Python defaults supply timezone-aware UTC objects (`default=utc_now`).
- Server defaults execute standard SQL functions (`server_default=text("CURRENT_TIMESTAMP")`).

### 2.4 Constraint & Index Naming Conventions
All constraints and indexes follow the standardized template defined in Architecture Document 05:
```python
POSTGRES_NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}
```

---

## 3. Connection Pooling & Transaction Management

### 3.1 Asynchronous Engine & Pool Configuration
The engine is created via SQLAlchemy 2.x `create_async_engine` bound to the `postgresql+asyncpg` driver:
- `pool_size`: Configurable via `DB_POOL_SIZE` (default: 20).
- `max_overflow`: Configurable via `DB_MAX_OVERFLOW` (default: 10).
- `pool_timeout`: Configurable via `DB_POOL_TIMEOUT` (default: 30.0s).
- `pool_recycle`: Configurable via `DB_POOL_RECYCLE` (default: 1800s / 30 min).
- `pool_pre_ping`: Enabled (`True`) to transparently discard dead socket connections.

### 3.2 Explicit Transaction Boundaries
Two primary patterns manage transaction boundaries:
1. **HTTP Request Scope (`get_db`)**:
   - Injected into FastAPI route handlers via `Depends(get_db)`.
   - Executes `await session.commit()` upon successful handler execution.
   - Executes `await session.rollback()` upon any unhandled exception before closing the session.
2. **Background Worker / Task Scope (`transactional_session`)**:
   - Async context manager for Celery tasks, scripts, and domain services:
     ```python
     async with transactional_session() as session:
         # explicit transaction block
         ...
     ```
   - Automatically begins an explicit transaction (`async with session.begin():`), commits on exit, and rolls back on failure.

---

## 4. Multi-Tenant Database Isolation & PostgreSQL RLS

### 4.1 PostgreSQL Role Partitioning & Privilege Separation
In strict conformance with Architecture Document 04 Section 1:
- **`postgres` (Bootstrap / Cloud DBA Superuser)**:
  - Used exclusively during container creation (`init-db.sql`) to install extensions and bootstrap roles.
  - Never used by the application runtime or CI tests.
- **`aihr_migration_user` (Privileged Migration / Schema Owner Role)**:
  - Created with `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`.
  - Owns schema `public` and all tenant-scoped tables (`candidate_document_embeddings`, `job_embeddings`, `organization_memberships`, etc.).
  - Used strictly by Alembic for DDL migrations (`DATABASE_MIGRATION_URL` / `DATABASE_SYNC_URL`).
- **`aihr_app_user` (Restricted Application Runtime Role)**:
  - Created with `NOSUPERUSER`, `NOBYPASSRLS`, `NOCREATEDB`, `NOCREATEROLE`.
- **Zero Hardcoded Role Credentials, Socket Detection & Controlled Reconciliation**:
  - `infrastructure/scripts/init-db.sql` and `infrastructure/scripts/init-db.sh` contain no hardcoded password literals.
  - Distinguishes Docker container entrypoint initialization (`IS_DOCKER_ENTRYPOINT=true`) vs external execution: inside `/docker-entrypoint-initdb.d/`, connects directly via local Unix domain socket (`/var/run/postgresql`) without passing external service hostnames.
  - Role distinctness validation: immediately fails if `POSTGRES_SUPERUSER`, `POSTGRES_MIGRATION_USER`, and `POSTGRES_APP_USER` collide, preventing accidental privilege escalation or ownership aliasing.
  - `init-db.sql` asserts mutual distinctness in a PL/pgSQL block before creating or altering any roles, schemas, or privileges.
  - Alembic migrations dynamically resolve the unprivileged runtime role from `app.core.config.get_settings()` (with environment variable fallback), validate identifier syntax, and reject collision with superuser or migration roles.
  - Ingests configured credentials directly from environment variables (`POSTGRES_MIGRATION_PASSWORD`, `POSTGRES_PASSWORD`, `PGPASSWORD`) via psql `\getenv`.
  - Employs safely quoted psql identifiers (`:"effective_mig_user"`, `:"effective_app_user"`) and string literals (`:'mig_password'`, `:'app_password'`).
  - Outside development (`ENVIRONMENT != development`), `init-db.sh` strictly forbids silent fallbacks: missing bootstrap, migration, or runtime secrets cause immediate failure with a clear error message and zero secret exposure.
  - Production `docker-compose.yml` requires explicit secrets via `${VAR:?error}` syntax, while local developer convenience is maintained via `docker-compose.dev.yml` overrides.
  - Idempotently reconciles passwords for both freshly created and pre-existing roles during controlled bootstrap without exposing secrets in logs or CLI process listings (`ps aux`).
  - Does **NOT** own any tenant-scoped tables, ensuring table-owner RLS bypass is impossible.
  - Granted restricted DML permissions (`SELECT`, `INSERT`, `UPDATE`, `DELETE`) via `ALTER DEFAULT PRIVILEGES`.
  - Used by the FastAPI runtime and Celery background workers (`DATABASE_URL`).
  - Fully subject to PostgreSQL Row-Level Security at all times.

### 4.2 In-Memory Cache & Message Broker Authentication (Redis 7)
- **Mandatory Authentication**: Redis 7 is deployed with mandatory authentication (`--requirepass`) across both production and development environments.
- **Production Secret Validation**: In production/staging, `REDIS_PASSWORD` must be explicitly configured and non-empty; placeholder values are strictly rejected.
- **URL & Broker Consistency**: Pydantic configuration (`app.core.config.Settings`) parses and enforces that `REDIS_URL`, `CELERY_BROKER_URL`, and `CELERY_RESULT_BACKEND` include matching authentication credentials whenever `REDIS_PASSWORD` is configured. Unauthenticated Redis URLs or password mismatches are immediately rejected at application startup.
- **Connection Pool Authentication**: Asynchronous Redis connection pools created via `app.core.redis.create_redis_pool` rely on `REDIS_URL` as the single authoritative connection descriptor. Because `REDIS_URL` already embeds the authentication credentials (`redis://:<password>@<host>:<port>/<db>`), `ConnectionPool.from_url` extracts and applies credentials directly from the URL rather than supplying the password separately.

### 4.2 Two-Tier Row-Level Security (RLS) Policy Model
Conforming to Architecture Document 04 Section 2, all tenant-scoped tables implement:
1. `ALTER TABLE <table_name> ENABLE ROW LEVEL SECURITY;`
2. `ALTER TABLE <table_name> FORCE ROW LEVEL SECURITY;`
3. **Base Permissive Policy (`AS PERMISSIVE`)**:
   - Evaluated first using boolean `OR`.
   - Grants runtime access to the unprivileged application role (`aihr_app_user`):
     ```sql
     CREATE POLICY <name>_app_user_perm ON <table_name>
         AS PERMISSIVE FOR ALL TO aihr_app_user
         USING (true) WITH CHECK (true);
     ```
4. **Mandatory Restrictive Tenant Isolation Policy (`AS RESTRICTIVE`)**:
   - Evaluated after permissive policies using boolean `AND`.
   - Unconditionally filters rows by the active transaction-local tenant context:
     ```sql
     CREATE POLICY <name>_tenant_restrict ON <table_name>
         AS RESTRICTIVE FOR ALL
         USING (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid)
         WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
     ```

### 4.3 Transaction-Local Tenant Context & Pool Defense
- **Transaction-Local Setting**: The authenticated tenant context is set using `SELECT set_config('app.current_tenant_id', :tenant_id, true)` (`is_local = true`). PostgreSQL automatically reverts the setting at transaction `COMMIT` or `ROLLBACK`.
- **Pool Checkin Cleanup Listener**: As defense-in-depth against accidental session-level pollution (`is_local = false`), SQLAlchemy's connection checkin listener resets `app.current_tenant_id` to empty string and commits the reset. If cleanup fails, the connection record is invalidated (`connection_record.invalidate(exc)`) to prevent reuse.
- **Fail-Safe Missing Context**: If `app.current_tenant_id` is unset or empty, `current_setting('app.current_tenant_id', true)` returns `NULL`, causing the equality comparison to evaluate to `UNKNOWN` (falsy in SQL). All `SELECT` queries return 0 rows, and mutations are rejected.

---

## 5. pgvector Integration & Embedding Architecture

### 5.1 Extension Activation
The `vector` extension is enabled through Alembic migration revision `002_db_foundation_pgvector`:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```

### 5.2 Model Registry Table: `embedding_models` (Table 10)
A platform-global model catalog validating providers, dimensions, and activation state:
- Primary Key: `model_identifier VARCHAR(100)`
- Columns: `provider VARCHAR(50)`, `expected_dimensions INTEGER`, `is_active BOOLEAN`, `created_at TIMESTAMPTZ`
- Check Constraint: `expected_dimensions IN (1536, 1024, 768)`
- Unique Constraint: `(model_identifier, expected_dimensions)`
- Seeded Models:
  1. `text-embedding-3-small` (OpenAI, 1536 dimensions)
  2. `amazon.titan-embed-text-v1` (AWS Bedrock, 1536 dimensions)
  3. `cohere.embed-english-v3` (AWS Bedrock, 1024 dimensions)
  4. `bge-base-en-v1.5` (HuggingFace, 768 dimensions)

### 5.3 Dimension-Safe Vector Storage Tables
Conforming to Architecture Document 05 Section 2.B & 2.C:
- **`candidate_document_embeddings` (Table 22)**: Stores dense representations of parsed resumes and candidate portfolios.
- **`job_embeddings` (Table 23)**: Stores dense representations of job descriptions and hiring requirements.
- **Model-to-Dimension Integrity**: Enforced via composite foreign key referencing `embedding_models(model_identifier, expected_dimensions)`:
  ```sql
  CONSTRAINT fk_cand_emb_model_dims
      FOREIGN KEY (model_identifier, vector_dimensions)
      REFERENCES embedding_models(model_identifier, expected_dimensions)
      ON DELETE RESTRICT
  ```
- **Exactly-One-Vector-Column CHECK Constraint**:
  ```sql
  CONSTRAINT chk_cand_emb_dimensions CHECK (
      (vector_dimensions = 1536 AND embedding_1536 IS NOT NULL AND embedding_1024 IS NULL AND embedding_768 IS NULL) OR
      (vector_dimensions = 1024 AND embedding_1024 IS NOT NULL AND embedding_1536 IS NULL AND embedding_768 IS NULL) OR
      (vector_dimensions = 768  AND embedding_768 IS NOT NULL  AND embedding_1536 IS NULL AND embedding_1024 IS NULL)
  )
  ```
- **Partial HNSW Cosine Distance Indexes**:
  Indexes are created with valid PostgreSQL 16 syntax (`WITH` parameters preceding `WHERE` clause) using `vector_cosine_ops` with `m = 16` and `ef_construction = 64`:
  ```sql
  CREATE INDEX idx_cand_emb_1536 ON candidate_document_embeddings 
      USING hnsw (embedding_1536 vector_cosine_ops)
      WITH (m = 16, ef_construction = 64)
      WHERE embedding_1536 IS NOT NULL;
  ```

### 5.4 Cosine Similarity Search Service (`app.modules.embeddings.service`)
- `store_candidate_document_embedding()` / `store_job_embedding()`: Validates model existence, active status, and vector dimensions before persisting to the appropriate typed vector column.
- `search_similar_candidate_documents()`: Executes tenant-scoped nearest-neighbor similarity searches using pgvector's cosine distance operator (`<=>`). Returns sorted tuples of `(CandidateDocumentEmbedding, similarity_score)` where $\text{similarity} = 1 - \text{cosine\_distance}$.

---

## 6. Alembic Migration History

| Revision ID | Description | Down Revision | Tables & Infrastructure Created |
|:---|:---|:---|:---|
| `001_auth_identity` | Initial authentication, identity, tenancy, and revocation outbox schema (Step 3.3). | `None` | `organizations`, `users`, `candidate_user_profiles`, `roles`, `permissions`, `role_permissions`, `organization_memberships`, `user_sessions`, `session_token_history`, `auth_revocation_outbox` |
| `002_db_foundation_pgvector` | Database foundation, pgvector extension, model registry, and vector tables (Step 3.4). | `001_auth_identity` | `pgvector` extension, `embedding_models`, `candidate_document_embeddings`, `job_embeddings`, HNSW indexes, RLS policies |

---

## 7. Automated Testing Suite

The database test suite covers all categories specified in the requirements:

### Unit Tests (`backend/tests/test_database.py`) — 37 Tests
1. `test_metadata_naming_conventions`: Confirms canonical PostgreSQL naming conventions.
2. `test_base_mixins_columns`: Verifies `TimestampMixin` and `TenantScopedMixin`.
3. `test_timezone_aware_timestamp_handling`: Verifies timezone-aware UTC datetime generation.
4. `test_get_engine_and_factory`: Verifies engine and sessionmaker creation.
5. `test_get_db_session_lifecycle_commit`: Verifies auto-commit on success.
6. `test_get_db_session_lifecycle_rollback_on_error`: Verifies auto-rollback on error.
7. `test_get_db_uses_request_app_state_session_factory`: Verifies app-state instance isolation.
8. `test_check_database_health_success`: Verifies database health probe returns True.
9. `test_check_database_health_failure`: Verifies database health probe returns False on timeout.
10. `test_pool_checkin_listener_failure_invalidates_connection`: Confirms connection invalidation on error.
11. `test_alembic_config_validation`: Validates `alembic.ini` parsing and location.
12. `test_transactional_session_commits_on_success`: Verifies transaction block commits on success.
13. `test_transactional_session_rolls_back_on_exception`: Verifies transaction block rolls back on failure.
14. `test_embedding_models_schema_and_approved_catalog`: Validates `EmbeddingModel` and 4 approved models.
15. `test_vector_embedding_tables_schema_and_constraints`: Validates vector columns and check constraints.
16. `test_store_embedding_rejects_unregistered_model`: Rejects unregistered model identifiers.
17. `test_store_embedding_rejects_inactive_model`: Rejects deactivated/deprecated models.
18. `test_store_job_embedding_validation`: Validates vector dimensions for job embeddings.
19. `test_embedding_model_registry_exact_canonical_contents`: Validates exact 4 canonical models in model registry.
20. `test_search_similar_candidate_documents_rejects_unsupported_dimensions`: Rejects invalid query dimensions.
21. `test_search_similar_candidate_documents_rejects_empty_query_vector`: Rejects zero-length query vectors.
22. `test_search_similar_candidate_documents_rejects_nan_and_inf_values`: Rejects non-finite floating point vector components.
23. `test_search_similar_candidate_documents_rejects_invalid_limits`: Rejects limits <= 0 or > 100.
24. `test_search_similar_candidate_documents_rejects_unregistered_model`: Rejects query model not in registry.
25. `test_search_similar_candidate_documents_rejects_inactive_model`: Rejects inactive model queries.
26. `test_init_db_sql_no_hardcoded_credentials_and_nocreatedb`: Verifies SQL script uses `\getenv` and enforces `NOCREATEDB`.
27. `test_init_db_sh_entrypoint_security`: Verifies shell script wraps execution safely and quotes identifiers.
28. `test_init_db_sh_missing_secrets_failure_outside_development`: Verifies `init-db.sh` fails immediately without silent fallbacks when required secrets are missing outside development.
29. `test_init_db_sh_local_development_initialization`: Verifies `init-db.sh` sets convenient local development defaults when `ENVIRONMENT=development`.
30. `test_env_example_contains_no_development_credentials_and_no_development_environment`: Verifies `.env.example` contains zero development passwords and requires explicit environment configuration.
31. `test_env_dev_example_contains_development_configuration`: Verifies `.env.dev.example` provides complete local development defaults and Docker Compose commands.
32. `test_docker_compose_enforces_mandatory_secrets_and_rejects_missing_values`: Verifies main `docker-compose.yml` enforces explicit secrets via `${VAR:?error}` syntax and rejects silent fallbacks.
33. `test_init_db_sh_role_collision_rejection`: Verifies `init-db.sh` validates role distinctness and rejects collisions between superuser, migration, and runtime users.
34. `test_init_db_sql_role_collision_check`: Verifies `init-db.sql` includes a strict role distinctness PL/pgSQL assertion before role creation or privilege grants.
35. `test_alembic_migration_role_collision_rejection`: Verifies Alembic migrations reject runtime role colliding with superuser or migration role.
36. `test_alembic_custom_app_role_resolution`: Verifies Alembic `_get_app_role()` dynamically resolves from `get_settings()` and validates identifier syntax.
37. `test_redis_client_authenticated_connection_pool`: Verifies Redis connection pool extracts and enforces authentication directly from the authoritative `REDIS_URL`.

### Configuration Tests (`backend/tests/test_config.py`) — 22 Tests
Extensive testing for environment resolution, production security rules, and Redis/Celery URL password matching:
- Validates production rejections for insecure defaults (`test_production_rejects_insecure_defaults`).
- Validates production acceptance with full secrets (`test_production_accepts_valid_secrets`).
- Validates Redis authentication configuration in development (`test_redis_authentication_in_dev`).
- Validates production rejection of missing `REDIS_PASSWORD` (`test_production_rejects_missing_redis_password`).
- Validates rejection of unauthenticated `REDIS_URL` or Celery broker URLs when `REDIS_PASSWORD` is configured (`test_redis_password_requires_matching_redis_url_password`, `test_redis_password_requires_matching_celery_broker_url_password`).
- Validates URL-encoded password matching (`test_redis_password_matches_url_encoded_password`).

### Integration Tests (`backend/tests/integration/test_postgres_lifecycle.py`) — 22 Tests
1. `test_postgres_connection_and_session_lifecycle`: Live connectivity and query execution.
2. `test_postgres_commit_and_rollback_behavior`: Transaction rollback discards uncommitted mutations.
3. `test_postgres_transaction_local_tenant_context`: Parameterized `set_config` transaction scoping.
4. `test_postgres_tenant_context_does_not_leak_across_pooled_connection_reuse`: Pool connection checkout safety.
5. `test_postgres_deliberate_session_level_tenant_context_cannot_leak_across_pool`: Checkin hook resets session settings.
6. `test_alembic_upgrade_head_and_revision_state`: Schema upgrade and revision tracking.
7. `test_postgres_concurrent_refresh_token_rotation_serializes_and_detects_reuse`: Row-lock serialization.
8. `test_postgres_concurrent_backup_code_redemption_serializes`: MFA backup code serialization.
9. `test_postgres_cross_tenant_role_assignment_trigger_rejection`: Database trigger rejects cross-tenant roles.
10. `test_postgres_state_c_redis_outage_authoritative_session_validation`: Outage fallback against authoritative DB.
11. `test_postgres_token_history_multi_rotation_and_old_token_reuse_detected`: Token reuse history protection.
12. `test_postgres_state_a_micro_validation_rejects_revoked_and_expired_session`: State A 30s micro-validation.
13. `test_postgres_pgvector_extension_and_model_registry`: Extension verification and model registry seeding.
14. `test_postgres_vector_dimension_check_constraints_and_foreign_keys`: Check constraints and composite FK enforcement.
15. `test_postgres_vector_insertion_and_cosine_similarity_search`: High-dimensional vector insert and cosine search.
16. `test_postgres_runtime_role_and_privileges_verification`: Verifies runtime role has `NOSUPERUSER`, `NOBYPASSRLS`, and does not own tenant tables.
17. `test_postgres_vector_tenant_isolation_under_rls`: Cross-tenant vector isolation under PostgreSQL RLS connecting directly via application runtime credentials without test role workarounds.
18. `test_postgres_embedding_model_registry_exact_seeded_contents`: Verifies live database contains exact 4 canonical models from architecture specification.
19. `test_postgres_vector_similarity_search_hardened_validation_integration`: Verifies live database rejection of invalid limits, empty/NaN vectors, missing/inactive models, and dimension mismatches.
20. `test_postgres_hnsw_indexes_exist_and_downgrade_upgrade_lifecycle`: HNSW index validation and reversible migrations.
21. `test_postgres_vector_downgrade_preserves_external_dependent_objects_and_extension`: Verifies safe non-cascading downgrade preserving extension and external vector objects.
22. `test_postgres_role_initialization_with_custom_credentials_and_reconciliation`: Genuine PostgreSQL credential reconciliation integration test that executes the actual `init-db.sh` / `init-db.sql` bootstrap mechanism with custom credentials, verifies authentication, re-executes bootstrap with rotated credentials to prove database-level password reconciliation, verifies new credentials succeed and old credentials are rejected, verifies catalog attributes (`rolsuper=false, rolbypassrls=false, rolcreatedb=false, rolcreaterole=false`), verifies runtime role does not own tenant-scoped tables and cannot bypass RLS, and cleans up test roles safely.

---

## 8. Development & Production Deployment Workflows

### 8.1 Local Development Workflow
Local development provides two isolated environments: containerized development (where the backend runs inside Docker containers) and host-based development (where the backend runs on the developer workstation against dockerized infrastructure services):

#### A. Containerized Development (Full Docker Compose Stack)
Uses `.env.dev.example` with internal container network hostnames (`postgres`, `redis`):
```bash
# 1. Copy containerized development environment template
cp .env.dev.example .env.dev

# 2. Launch complete local development stack (with live hot reload & debug logging)
docker compose --env-file .env.dev -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.dev.yml up -d

# 3. View logs
docker compose --env-file .env.dev -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.dev.yml logs -f
```

#### B. Host-Based Development (Local Python / Next.js against Docker Services)
Uses `.env.local.example` with host-accessible loopback bindings (`localhost:5432`, `localhost:6379`). Note that ports are strictly bound to `127.0.0.1` by `docker-compose.dev.yml` to prevent network exposure:
```bash
# 1. Launch only database and cache services
docker compose --env-file .env.dev -f infrastructure/docker/docker-compose.yml -f infrastructure/docker/docker-compose.dev.yml up -d postgres redis

# 2. Copy host-based local environment template
cp .env.local.example .env

# 3. Run migrations and local FastAPI server
cd backend
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

### 8.2 Production & Staging Deployment Workflow
Production deployments require explicit configuration of high-entropy secrets and environment identification:

```bash
# 1. Copy production environment template
cp .env.example .env

# 2. Configure mandatory production secrets in .env:
#    - ENVIRONMENT=production
#    - POSTGRES_SUPERUSER_PASSWORD=<min-32-char-high-entropy-secret>
#    - POSTGRES_MIGRATION_PASSWORD=<min-32-char-high-entropy-secret>
#    - POSTGRES_PASSWORD=<min-32-char-high-entropy-secret>
#    - JWT_SECRET_KEY, MFA_ENCRYPTION_KEY, BACKUP_CODE_PEPPER

# 3. Launch hardened production stack (docker-compose will abort immediately if any required secret is missing)
docker compose --env-file .env -f infrastructure/docker/docker-compose.yml up -d
```

### 8.3 Quality Gates & Testing Instructions

### Prerequisites
- Python 3.11 with virtual environment initialized (`poetry install` or `pip install -r backend/requirements-dev.txt`).
- PostgreSQL 16 with `pgvector` extension enabled (available via Docker Compose: `infrastructure/docker/docker-compose.yml`).

### Running Quality Checks
```bash
# 1. Python compilation check
python -m compileall backend/app backend/tests backend/alembic

# 2. Ruff linting & formatting checks
ruff check backend/app backend/tests
ruff format --check backend/app backend/tests

# 3. Mypy strict type checking
mypy --config-file backend/pyproject.toml backend/app

# 4. Full Pytest test suite
pytest backend/tests -v --cov=app --cov-report=term-missing
```

---

## 9. Known Limitations & Deferred Items
- **Candidate & Job Documents Domain Tables**: In adherence to the strict boundary restrictions of Step 3.4, business recruitment tables (`candidate_profiles`, `candidate_documents`, `jobs`, `applications`) are not prematurely created in this milestone. The vector tables `candidate_document_embeddings` and `job_embeddings` are established as foundation tables with composite model-registry foreign keys; the composite foreign keys linking `(tenant_id, document_id)` to `candidate_documents` and `(tenant_id, job_id)` to `jobs` will be connected in Phase 4 (Candidate Dossiers) and Phase 5 (Job Requisitions).
