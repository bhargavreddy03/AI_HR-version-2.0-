# AI-Powered Recruitment & HR Intelligence Platform (VER 2.0)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/bhargavreddy03/AI_HR-version-2.0-)
[![Architecture](https://img.shields.io/badge/Architecture-Approved-success)](docs/architecture/STEP_2_FINAL_APPROVAL.md)
[![Milestone](https://img.shields.io/badge/Milestone-Step_3.10_Completed-green)](docs/implementation/STEP_3_10_PHASE_1_FOUNDATIONAL_SKILL_REGISTRY_AND_DOCUMENT_INGESTION.md)
[![Tests](https://img.shields.io/badge/Tests-421%20Passed-brightgreen)](backend/tests/)
[![Coverage](https://img.shields.io/badge/Module%20Coverage-87.91%25-brightgreen)](backend/tests/)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.111+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-336791?logo=postgresql)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-5.4+-37814A?logo=celery)](https://docs.celeryq.dev/)

A next-generation enterprise SaaS platform designed for multi-tenant candidate acquisition, secure document ingestion, deterministic technical skill extraction, explainable neural candidate matching, structured interview management, and predictive workforce analytics.

Architected as a high-performance **modular monolith** adhering strictly to the canonical system specifications documented in [`docs/architecture/`](docs/architecture/).

- **Repository**: [https://github.com/bhargavreddy03/AI_HR-version-2.0-](https://github.com/bhargavreddy03/AI_HR-version-2.0-)

---

## 1. System Architecture & Technology Stack

The platform is engineered for enterprise multi-tenancy, zero-trust distributed authorization, and deterministic AI/ML workflows:

| Layer | Technology | Primary Purpose |
|:---|:---|:---|
| **Frontend Portal** | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS | Multi-portal web application for candidates, recruiters, hiring managers, and tenant administrators. |
| **Backend Core** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async) | High-throughput asynchronous modular API, validation, and domain service coordination. |
| **Primary Database** | PostgreSQL 16 + `pgvector` extension | Authoritative relational data store, composite multi-tenant keys, native vector similarity search, and PostgreSQL Row-Level Security (RLS) policies. |
| **Distributed Cache & Broker** | Redis 7 (ElastiCache compatible) | Monotonic session token verification, rate limiting, and background task queue. |
| **Background Processing** | Celery 5.4+ with Redis broker | Asynchronous document extraction (`document_processing` queue), resume parsing, embedding generation, scoring pipelines, and scheduled maintenance. |
| **Document Ingestion & PDF Extraction** | `pdfplumber` + Custom `TextNormalizer` | Memory-bounded PDF parsing, active script/malware blocking, and deterministic skill phrase extraction. |
| **Cloud Object Storage** | AWS S3 / MinIO (S3-Compatible) | Tenant-isolated document storage (`tenants/{tenant_id}/documents/{year}/{month}/{random_id}.pdf`), AES-256 SSE, SHA-256 integrity verification, and time-limited presigned URLs. |
| **Testing & Verification** | Pytest, AnyIO, Locust, Ruff | 421 passing unit, regression, security, and concurrency tests with 87%+ code coverage. |

---

## 2. Monorepo Repository Structure

```
VER 2.0/
├── .github/
│   └── workflows/ci.yml       # Continuous integration pipeline (linting, typechecks, tests)
├── backend/
│   ├── alembic/               # Database migrations (001_core, 002_vector, 003_documents)
│   ├── app/
│   │   ├── api/v1/            # API v1 versioned routers (health, tasks, auth, documents)
│   │   ├── core/              # Global configuration, database engine, Celery app, security
│   │   │   ├── security/      # Antivirus scanner, file magic bytes validation, rate limiting
│   │   │   └── tasks/         # BaseTask, idempotent_task decorator, telemetry
│   │   └── modules/           # Self-contained domain modules (modular monolith)
│   │       ├── auth/          # Identity, sessions, JWT token lifecycle, MFA TOTP, Argon2id
│   │       ├── organizations/ # Tenants, departments, roles, memberships, RLS policies
│   │       ├── documents/     # S3 storage, PDF extractor, OCR fallback, document lifecycle
│   │       ├── screening/     # Matching engine, pgvector embeddings, and skill registry
│   │       │   └── skills/    # 10-domain taxonomy, TextNormalizer, ExactMatcher
│   │       ├── candidates/    # Candidate dossiers, profiles, skills (scaffolded)
│   │       ├── jobs/          # Requisitions, job posts, hiring criteria (scaffolded)
│   │       ├── pipeline/      # Hiring stages finite-state-machine (FSM) (scaffolded)
│   │       ├── interviews/    # Scheduling, panels, scorecards (scaffolded)
│   │       ├── assessments/   # Automated question generation (scaffolded)
│   │       ├── reporting/     # Aggregations, export pipelines (scaffolded)
│   │       └── audit/         # Immutable compliance and event logs (scaffolded)
│   ├── tests/                 # 421 comprehensive unit, integration, and load tests
│   │   ├── test_skill_registry.py     # 53 skill registry and exact matcher tests
│   │   ├── test_document_ingestion.py # 30 document extraction, S3, and task tests
│   │   ├── test_document_api.py       # 7 document REST API and RBAC tests
│   │   └── load/                      # Locust workload definitions and performance fixtures
│   ├── pyproject.toml         # Python packaging, Poetry, and test configuration
│   ├── requirements.txt       # Production dependency manifest
│   ├── requirements-dev.txt   # Development dependencies (ruff, mypy, pytest)
│   └── Dockerfile             # Multi-stage production container build
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js 14 App Router portal route groups
│   │   ├── components/        # Reusable UI component library
│   │   ├── lib/               # Utility functions, API client wrappers
│   │   └── types/             # Shared TypeScript declarations
│   ├── public/                # Static assets, logos, icons
│   ├── package.json           # Frontend dependency manifest
│   ├── tsconfig.json          # Strict TypeScript compiler options
│   └── tailwind.config.ts     # Tailwind CSS theme configuration
├── infrastructure/
│   ├── docker/
│   │   ├── docker-compose.yml     # PostgreSQL 16 + pgvector, Redis, API, and Web services
│   │   └── docker-compose.dev.yml # Local development container overrides
│   └── scripts/init-db.sql    # Database extension initialization
├── docs/
│   ├── architecture/          # Step 2 Architectural Specifications (APPROVED)
│   └── implementation/        # Step 3 Implementation Tracking Documents (Steps 3.1 - 3.10)
├── .env.example               # Comprehensive environment variable template
├── .gitignore                 # Enterprise monorepo gitignore rules
└── README.md                  # Root documentation (this file)
```

---

## 3. Core Modules & Step 3.10 Features

### 3.1 Foundational Skill Registry & Deterministic Matcher
- **10-Domain Taxonomy**: Ported from legacy AI HR comprising 200+ canonical technical competencies and 300+ normalized aliases across `Programming Languages`, `Core CS`, `Web & Frontend`, `Data & AI/ML`, `Databases`, `DevOps & Cloud`, `Cybersecurity`, `Emerging Tech`, `Mobile`, and `Tools & Practices`.
- **Protected Technical Symbol Normalization**: `TextNormalizer` standardizes Unicode NFKC and strips noise while preserving special technical expressions (`C++`, `C#`, `.NET`, `Node.js`, `CI/CD`) using alphabetic placeholders (`XTECH...X`) before punctuation cleaning.
- **Longest-First Non-Overlapping Span Reservation**: `ExactMatcher` pre-sorts candidates longest-first and claims character spans during regex evaluation. This mathematically eliminates substring false positives:
  - In `"5 years of modern C++ development"`, `C++` claims span `[19, 22]`; single-letter `C` cannot overlap and is rejected.
  - In `"Proficient in C and Python"`, standalone `C` correctly matches `[14, 15]`.
  - In `"Data Structures and Algorithms"`, the full candidate claims the span; redundant sub-matches on `Algorithms` are suppressed.
- **Demographic Neutrality Protection**: Protected demographic attributes (gender, race, religion, marital status, age) are strictly excluded from the taxonomy and cannot be extracted as skills.

### 3.2 Secure Document Ingestion Pipeline
- **Defense-in-Depth File Security**: Validates 10 MB file bounds, `%PDF-` magic-byte signatures, blocks embedded active executable triggers (`/JavaScript`, `/Launch`, `/EmbeddedFiles`), and abstracts antivirus inspection.
- **S3-Compatible Object Storage**: `StorageService` implements deterministic tenant isolation (`tenants/{tenant_id}/documents/{year}/{month}/{random_id}.pdf`), pre-upload and post-download SHA-256 verification, AES-256 SSE, time-limited presigned download URLs, and offline in-memory fallback for unit tests.
- **Modular PDF Text Extraction**: `PDFExtractorService` wraps `pdfplumber` with resource limits (50 pages max, 15s timeout, 500k characters max) and computes extraction quality scores. Detects scanned or image-only PDFs (`requires_ocr=True`).
- **Pluggable OCR Fallback Architecture**: `NullOCRProvider` explicitly transitions documents to `OCR_REQUIRED` when no external OCR is configured (preventing false success claims). `MockOCRProvider` is available for testing.
- **Controlled Lifecycle State Machine**: Concurrency-safe state transitions (`UPLOADED` -> `QUEUED` -> `PROCESSING` -> `COMPLETED`, `OCR_REQUIRED`, `FAILED`, `DELETION_PENDING`, `DELETED`) with PostgreSQL Row-Level Security (RLS) enforcement.
- **Asynchronous Celery Processing**: `process_document_task` routed to `document_processing` queue with `@idempotent_task` deduplication, jittered exponential retry backoff, and periodic orphaned document recovery (`recover_orphaned_documents_task`).
- **Tenant-Scoped Deduplication**: Uploading an identical document (matching SHA-256) within the same tenant returns the existing document record with `is_duplicate=True` without re-uploading to S3.

### 3.3 Document REST API (`/api/v1/documents`)
| Method | Endpoint | RBAC Permission | Description |
|:---|:---|:---|:---|
| `POST` | `/api/v1/documents/upload` | `documents:upload` | Multipart file upload with antivirus checks, tenant RLS, deduplication, and Celery dispatch. Returns 201 (or 200 for duplicates). |
| `GET` | `/api/v1/documents/{id}` | `documents:read` | Authoritative lifecycle status and processing metadata. |
| `GET` | `/api/v1/documents/{id}/extraction` | `documents:read` | Structured text extraction results, page texts, and quality score. |
| `GET` | `/api/v1/documents/{id}/download-url` | `documents:read` | Generates authorized, time-limited presigned S3 download URL. |
| `DELETE` | `/api/v1/documents/{id}` | `documents:delete` | Purges document database records and underlying S3 object storage payload. |

---

## 4. Local Development Setup

### Prerequisites
- **Python**: Version 3.11.x or higher
- **Node.js**: Version 18.x or 20.x LTS (with `npm`)
- **Docker & Docker Compose**: For local PostgreSQL 16 (with pgvector) and Redis 7

### Quick Start

1. **Clone & Configure Environment**:
   ```bash
   git clone https://github.com/bhargavreddy03/AI_HR-version-2.0-.git
   cd AI_HR-version-2.0-
   cp .env.example .env
   ```

2. **Backend Setup**:
   ```bash
   cd backend
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate

   pip install -r requirements-dev.txt
   ```

3. **Frontend Setup**:
   ```bash
   cd frontend
   npm install
   ```

4. **Spin up Local Services with Docker Compose**:
   ```bash
   docker compose -f infrastructure/docker/docker-compose.yml up -d
   ```

5. **Start Development Servers**:
   - Backend API:
     ```bash
     cd backend
     uvicorn app.main:app --reload --port 8000
     ```
     Access Swagger OpenAPI docs at: `http://localhost:8000/docs`
   - Frontend:
     ```bash
     cd frontend
     npm run dev
     ```
     Access Web Application at: `http://localhost:3000`

---

## 5. Testing & Code Quality

The platform enforces strict automated test verification and code hygiene across all modules:

### Running Test Suites
```bash
cd backend

# Run all unit and regression tests (421 tests)
pytest tests -m "not integration"

# Run skill registry and exact matcher tests (53 tests)
pytest tests/test_skill_registry.py -v

# Run document ingestion and S3 storage tests (30 tests)
pytest tests/test_document_ingestion.py -v

# Run document REST API and RBAC tests (7 tests)
pytest tests/test_document_api.py -v

# Run test coverage analysis (requires >= 83.0% coverage)
pytest tests/test_document_ingestion.py tests/test_skill_registry.py tests/test_document_api.py --cov=app/modules/screening/skills --cov=app/modules/documents --cov-report=term-missing
```

### Linting & Formatting
```bash
cd backend
ruff check .
ruff format --check .
mypy app/
```

---

## 6. Implementation Milestones

| Milestone | Status | Description | Documentation |
|:---|:---:|:---|:---|
| **Step 1** | Approved | Discovery & Requirements Analysis | [`docs/discovery/`](docs/discovery/) |
| **Step 2** | Approved | Enterprise Architecture Specification (16 Documents) | [`docs/architecture/STEP_2_FINAL_APPROVAL.md`](docs/architecture/STEP_2_FINAL_APPROVAL.md) |
| **Step 3.1** | Completed | Monorepo Foundation & Structure Initialization | [`docs/implementation/01_step_3_1_repository_foundation.md`](docs/implementation/01_step_3_1_repository_foundation.md) |
| **Step 3.2** | Completed | FastAPI Backend, Database Engine, Pool Safety & Configuration Guardrails | [`docs/implementation/STEP_3_2_BACKEND_FOUNDATION.md`](docs/implementation/STEP_3_2_BACKEND_FOUNDATION.md) |
| **Step 3.3** | Completed | Multi-Tenant Identity, Authentication & Session Verification | [`docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md`](docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md) |
| **Step 3.4** | Completed | PostgreSQL Database Foundation, Composite Keys & RLS Isolation | [`docs/implementation/STEP_3_4_DATABASE_FOUNDATION.md`](docs/implementation/STEP_3_4_DATABASE_FOUNDATION.md) |
| **Step 3.5** | Completed | Redis Caching & Celery Background Distributed Task Queue | [`docs/implementation/STEP_3_5_REDIS_CELERY.md`](docs/implementation/STEP_3_5_REDIS_CELERY.md) |
| **Step 3.6** | Completed | Docker Compose, Local Containerization & Service Orchestration | [`docs/implementation/STEP_3_6_DOCKER_ENVIRONMENT.md`](docs/implementation/STEP_3_6_DOCKER_ENVIRONMENT.md) |
| **Step 3.7** | Completed | Application Security Foundation, Antivirus Abstraction & Defense-in-Depth | [`docs/implementation/STEP_3_7_SECURITY_FOUNDATION.md`](docs/implementation/STEP_3_7_SECURITY_FOUNDATION.md) |
| **Step 3.8** | Completed | Testing Foundation, Automated CI Suites & Code Quality Gates | [`docs/implementation/STEP_3_8_TESTING_AND_CODE_QUALITY.md`](docs/implementation/STEP_3_8_TESTING_AND_CODE_QUALITY.md) |
| **Step 3.9** | Completed | Legacy AI HR Integration Preparation, Compliance Analysis & Architectural Blueprint | [`docs/implementation/STEP_3_9_LEGACY_INTEGRATION_PREPARATION.md`](docs/implementation/STEP_3_9_LEGACY_INTEGRATION_PREPARATION.md) |
| **Step 3.10** | Completed | Phase 1: Foundational Skill Registry & Secure Document Ingestion Pipeline | [`docs/implementation/STEP_3_10_PHASE_1_FOUNDATIONAL_SKILL_REGISTRY_AND_DOCUMENT_INGESTION.md`](docs/implementation/STEP_3_10_PHASE_1_FOUNDATIONAL_SKILL_REGISTRY_AND_DOCUMENT_INGESTION.md) |
| **Step 3.11** | Next | Phase 2: Candidate Profiles & Resume Section Extraction | Upcoming |
| **Step 3.12** | Pending | Phase 3: AI Screening, Neural Matching & Evaluation Engine | Upcoming |
| **Step 3.13** | Pending | Phase 4: Structured Interview Management & Analytics Dashboard | Upcoming |

---

## 7. Original Prototype Preservation

The original prototype files and historical training data remain 100% intact and unmodified in their historical directory:
- **Location**: `../AI HR/` (`C:\Users\bharg\OneDrive\Desktop\AI HR\AI HR`)
- **Artifacts Preserved**: Original Streamlit prototype (`app.py`), baseline training scripts (`train_models.py`, `preprocessing.py`), trained scikit-learn models (`models/`), and baseline resume dataset (`resume_dataset_1200.csv`).
- **Integrity Status**: **100% Intact and untouched**.
