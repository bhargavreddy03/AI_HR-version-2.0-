# AI-Powered Recruitment & HR Intelligence Platform (VER 2.0)

[![GitHub Repository](https://img.shields.io/badge/GitHub-Repository-blue?logo=github)](https://github.com/bhargavreddy03/AI_HR-version-2.0-)
[![Architecture](https://img.shields.io/badge/Architecture-Approved-success)](docs/architecture/STEP_2_FINAL_APPROVAL.md)
[![Milestone](https://img.shields.io/badge/Milestone-Step_3.3_Completed-green)](docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md)

A next-generation enterprise SaaS platform designed for multi-tenant candidate acquisition, automated resume ingestion, explainable neural candidate matching, structured interview management, and predictive workforce analytics.

Architected as a high-performance **modular monolith** adhering strictly to the canonical system specifications documented in [`docs/architecture/`](docs/architecture/).

- **Repository**: [https://github.com/bhargavreddy03/AI_HR-version-2.0-](https://github.com/bhargavreddy03/AI_HR-version-2.0-)

---

## 1. Architecture & Technology Stack

The platform is designed for enterprise scale, strict multi-tenant isolation via PostgreSQL Row-Level Security (RLS), and zero-trust distributed authorization:

| Layer | Technology | Primary Purpose |
|:---|:---|:---|
| **Frontend Portal** | Next.js 14 (App Router), React 18, TypeScript, Tailwind CSS | Multi-portal web application for candidates, recruiters, hiring managers, and tenant administrators. |
| **Backend Core** | Python 3.11+, FastAPI, Pydantic v2, SQLAlchemy 2.0 (Async) | High-throughput asynchronous modular API, validation, and domain service coordination. |
| **Primary Database** | PostgreSQL 16 + `pgvector` extension | Authoritative relational data store, composite multi-tenant keys, native vector similarity search, and RLS guards. |
| **Distributed Cache & Broker** | Redis 7 (ElastiCache compatible) | Monotonic session token verification, rate limiting, and background task queue. |
| **Background Processing** | Celery + Redis | Asynchronous OCR document parsing, embedding generation, scoring pipelines, and scheduled reports. |
| **Cloud Storage** | AWS S3 (Private Buckets) | Immutable document storage with strict time-limited pre-signed URL access. |

---

## 2. Monorepo Repository Structure

```
VER 2.0/
├── .github/
│   └── workflows/ci.yml       # Continuous integration pipeline (linting, typechecks, tests)
├── backend/
│   ├── app/
│   │   ├── core/              # Global configuration, logging, database engine setup
│   │   └── modules/           # Self-contained domain modules (modular monolith)
│   │       ├── auth/          # Identity, sessions, JWT token lifecycle
│   │       ├── organizations/ # Tenants, departments, roles, memberships
│   │       ├── candidates/    # Candidate dossiers, profiles, skills
│   │       ├── jobs/          # Requisitions, job posts, hiring criteria
│   │       ├── screening/     # Matching engine, pgvector embeddings
│   │       ├── pipeline/      # Hiring stages finite-state-machine (FSM)
│   │       ├── interviews/    # Scheduling, panels, scorecards
│   │       ├── assessments/   # Automated question generation
│   │       ├── documents/     # S3 presigned URLs, upload validation
│   │       ├── reporting/     # Aggregations, export pipelines
│   │       └── audit/         # Immutable compliance and event logs
│   ├── tests/                 # Unit, integration, and concurrency isolation test suites
│   ├── pyproject.toml         # Python packaging & Poetry configuration
│   ├── requirements.txt       # Production dependency manifest
│   ├── requirements-dev.txt   # Development dependencies (ruff, mypy, pytest)
│   ├── ruff.toml              # Fast Python linter & formatter configuration
│   └── Dockerfile             # Multi-stage container build
├── frontend/
│   ├── src/
│   │   ├── app/               # Next.js 14 App Router portal route groups
│   │   ├── components/        # Reusable UI component library
│   │   ├── lib/               # Utility functions, API client wrappers
│   │   └── types/             # Shared TypeScript declarations
│   ├── public/                # Static assets, logos, icons
│   ├── package.json           # Frontend dependency manifest
│   ├── tsconfig.json          # Strict TypeScript compiler options
│   ├── tailwind.config.ts     # Tailwind CSS theme configuration
│   └── Dockerfile             # Multi-stage production container build
├── infrastructure/
│   ├── docker/
│   │   ├── docker-compose.yml # PostgreSQL 16 + pgvector, Redis, API, and Web services
│   │   └── docker-compose.dev.yml # Local development container overrides
│   └── scripts/init-db.sql    # Database extension initialization
├── docs/
│   ├── architecture/          # Step 2 Architectural Specifications (APPROVED)
│   └── implementation/        # Step 3 Implementation Tracking Documents
├── .env.example               # Comprehensive environment variable template
├── .gitignore                 # Enterprise monorepo gitignore rules
└── README.md                  # Root documentation (this file)
```

---

## 3. Original Project Preservation

The original prototype files and historical training data are preserved in their original state and location:
- **Location**: `../AI HR/` (`C:\Users\bharg\OneDrive\Desktop\AI HR\AI HR`)
- **Artifacts Preserved**: Original Streamlit prototype (`app.py`), baseline training scripts (`train_models.py`, `preprocessing.py`), trained scikit-learn models (`models/`), and baseline resume dataset (`resume_dataset_1200.csv`).
- **Integrity Status**: **100% Intact and unmodified**.

---

## 4. Local Development Setup

### Prerequisites
- **Python**: Version 3.11.x or higher
- **Node.js**: Version 18.x or 20.x LTS (with `npm` or `pnpm`)
- **Docker & Docker Compose**: Recommended for local PostgreSQL 16 (with pgvector) and Redis 7

### Quick Start (Environment Setup)

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
   # On Windows:
   .venv\Scripts\activate
   # On Linux/macOS:
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

## 5. Development Quality & Linting Standards

- **Python Linting & Formatting**:
  ```bash
  cd backend
  ruff check .
  ruff format --check .
  mypy app/
  ```

- **Frontend Linting & Type Checking**:
  ```bash
  cd frontend
  npm run lint
  npx tsc --noEmit
  ```

---

## 6. Project Roadmap & Recent Updates

### Latest Activity
- **Step 3.3 Completed**: Implemented comprehensive Authentication & Global Identity Foundation. Built platform-global `users` and candidate-owned profiles, tenant-scoped `organization_memberships`, Argon2id password security, RFC 6238 TOTP MFA with AES-256-GCM encryption at rest, sliding refresh token rotation with reuse detection, atomic monotonic Redis Lua revocation scripts, HttpOnly cookie lifecycle with double-submit CSRF, and the complete 6-layer request validation pipeline with PostgreSQL RLS tenant context binding ([`docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md`](docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md)).
- **Step 3.2 Finalized & Audited**: Hardened asynchronous FastAPI backend foundation. Implemented persisted PostgreSQL connection pool tenant reset (`SELECT set_config('app.current_tenant_id', '', false)` + commit) with automatic invalidation on checkin failure, strict application-instance resource isolation across FastAPI lifespans (`app.state`), clean non-swallowing Alembic migration reporting, production database credential validation, RFC 7807 error responses, and 87%+ test coverage ([`docs/implementation/STEP_3_2_BACKEND_FOUNDATION.md`](docs/implementation/STEP_3_2_BACKEND_FOUNDATION.md)).
- **Step 3.1 Completed**: Repository foundation established. Monorepo folder layout created, FastAPI core initialized, Next.js 14 App Router configured, Docker Compose environment prepared, CI/CD pipeline defined, and architecture documentation synchronized.
- **Git Repository Connected**: Initialized tracking with remote `https://github.com/bhargavreddy03/AI_HR-version-2.0-.git`.

### Milestone Progress
- [x] **Step 1**: Discovery & Requirements Analysis (`docs/discovery/`)
- [x] **Step 2**: Enterprise Architecture Specification (`docs/architecture/STEP_2_FINAL_APPROVAL.md`)
- [x] **Step 3.1**: Monorepo Foundation & Structure Initialization (`docs/implementation/01_step_3_1_repository_foundation.md`)
- [x] **Step 3.2**: FastAPI Backend Foundation, Database Engine, Pool Safety & Configuration Guardrails (docs/implementation/STEP_3_2_BACKEND_FOUNDATION.md)
- [x] **Step 3.3**: Multi-Tenant Identity, Authentication & Session Verification (`docs/implementation/STEP_3_3_AUTHENTICATION_IDENTITY.md`)
- [ ] **Step 3.4**: Core ATS Domain Modules (Jobs, Candidates, Pipeline)
- [ ] **Step 3.5**: AI Screening, Neural Matching & Evaluation Engine
