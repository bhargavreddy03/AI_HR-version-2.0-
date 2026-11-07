# Implementation Roadmap & Phase Plan

This document establishes the dependency-aware, phased engineering implementation roadmap for building the enterprise ATS SaaS platform.

---

## 1. Phased Implementation Overview

```mermaid
gantt
    title ATS SaaS Implementation Roadmap
    dateFormat  YYYY-MM-DD
    section Foundation
    Phase 1: Repo & Tooling Foundation       :p1, 2026-11-10, 10d
    Phase 2: Auth, Identity & Tenancy        :p2, after p1, 14d
    Phase 3: Org Administration & RBAC       :p3, after p2, 10d
    section Core ATS
    Phase 4: Candidate Dossier & Resume S3   :p4, after p3, 14d
    Phase 5: Job Requisitions & Criteria     :p5, after p4, 10d
    Phase 6: Applications & Pipeline FSM     :p6, after p5, 14d
    section AI & Intelligence
    Phase 7: Resume Parsing & AI Screening   :p7, after p6, 18d
    Phase 8: Interviews & Assessments        :p8, after p7, 14d
    section Polish & Enterprise
    Phase 9: Collaboration & Notifications   :p9, after p8, 10d
    Phase 10: Analytics & Excel/PDF Reports  :p10, after p9, 10d
    Phase 11: Super Admin & SaaS Foundation  :p11, after p10, 10d
    Phase 12: Security Hardening & Staging   :p12, after p11, 14d
```

---

## 2. Phase-by-Phase Deliverables & Acceptance Criteria

### Phase 1: Repository Scaffolding & Development Foundation
- **Scope**: Initialize monorepo, Docker Compose (PostgreSQL 16 + pgvector, Redis), Poetry setup, Next.js 14 template, and pre-commit hooks (`ruff`, `mypy`).
- **Dependencies**: None.
- **Deliverables**: Working local development environment with passing CI pipeline stub.
- **Definition of Done**: `docker compose up` spins up healthy database, Redis, backend, and frontend containers.

### Phase 2: Identity, Authentication & Multi-Tenancy Foundation
- **Scope**: Implement `users`, `organizations`, `organization_memberships`, Argon2id password hashing, JWT HttpOnly cookies, and PostgreSQL RLS session listeners.
- **Dependencies**: Phase 1.
- **Deliverables**: Functional registration, login, email verification, and RLS tenant isolation suite.
- **Definition of Done**: 100% pass on automated cross-tenant leakage assertion tests.

### Phase 3: Organization Administration & RBAC
- **Scope**: Department management, team mapping, user invitations, role assignment, and granular permission enforcement middleware.
- **Dependencies**: Phase 2.
- **Deliverables**: Org Admin portal views and RBAC policy engine.

### Phase 4: Candidate Profiles & Private Resume S3 Storage
- **Scope**: Candidate dossier schemas, S3 presigned PUT URL generation, file validation, and checksum deduplication.
- **Dependencies**: Phase 3.
- **Deliverables**: Candidate portal profile manager and secure document store.

### Phase 5: Job Requisitions & Hiring Criteria
- **Scope**: Requisition lifecycle (`draft`, `published`, `closed`), skill weighting configuration (`weights_config`), and public careers job board.
- **Dependencies**: Phase 4.
- **Deliverables**: Recruiter job builder studio and candidate-facing public job listings.

### Phase 6: Applications & Recruitment Pipeline FSM
- **Scope**: Application submission, pipeline templates, stages, and validated transition engine (`VALID_TRANSITIONS`).
- **Dependencies**: Phase 5.
- **Deliverables**: Drag-and-drop recruiter Kanban board and candidate application tracking view.

### Phase 7: Resume Parsing, Skill Extraction & AI Screening
- **Scope**: Celery worker integration, `pdfplumber` + OCR fallback, `SkillExtractor` taxonomy integration, `pgvector` embeddings, and explainable matching engine.
- **Dependencies**: Phase 6.
- **Deliverables**: Automated screening studio with component-level score breakdowns and evidence quotes.

### Phase 8: Interviews, Calendar Scheduling & Assessments
- **Scope**: Interview slot booking, panel availability, iCal/ICS generation, structured scorecards, and rule-based/LLM interview question generator.
- **Dependencies**: Phase 7.
- **Deliverables**: Interview scheduling console and hiring manager scorecard submission portal.

### Phase 9: Team Collaboration & Automated Notifications
- **Scope**: Internal candidate comments with `@mentions`, email notifications, and automated stage transition alerts.
- **Dependencies**: Phase 8.
- **Deliverables**: Recruiter candidate discussion timeline and email notification dispatcher.

### Phase 10: Analytics Dashboard & Asynchronous Reporting
- **Scope**: Time-to-fill charts, recruiter activity funnels, Celery background Excel/PDF export generator, and S3 pre-signed report downloads.
- **Dependencies**: Phase 9.
- **Deliverables**: Comprehensive analytics dashboard and export generator.

### Phase 11: Platform Super Admin & SaaS Foundations
- **Scope**: Multi-tenant directory, subscription plan enforcement, AI provider API key configuration, and dead-letter queue monitoring.
- **Dependencies**: Phase 10.
- **Deliverables**: Super Admin operational portal with immutable administrative audit trails.

### Phase 12: Security Hardening, Penetration Testing & AWS Staging Deployment
- **Scope**: AWS ECS Fargate deployment via Terraform/CDK, RDS Multi-AZ, AWS WAF configuration, GDPR export/deletion verification, and load testing.
- **Dependencies**: Phase 11.
- **Deliverables**: Fully verified staging environment ready for commercial pilot onboarding.
