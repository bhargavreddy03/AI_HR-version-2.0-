# Product Requirements Document (PRD)

## 1. Executive Summary & Vision

The **AI HR Intelligence Platform** is a global, multi-tenant Software-as-a-Service (SaaS) Applicant Tracking System (ATS) and Recruitment Intelligence ecosystem. It bridges automated candidate relationship management, high-throughput document processing, explainable AI-driven candidate-job alignment, collaborative interview workflows, and regulatory compliance.

The platform is designed to serve five distinct stakeholder tiers:
1. **Candidates**: Seeking seamless application submission, profile control, interview scheduling, and data privacy governance.
2. **Recruiters / Talent Acquisition Specialists**: Requiring efficient candidate sourcing, screening, automated pipeline transitions, and collaborative hiring workflows.
3. **Hiring Managers**: Needing curated shortlists, structured interview scorecards, candidate comparisons, and role-scoped visibility without global data exposure.
4. **Organization Administrators**: Governing enterprise tenant settings, role-based access control (RBAC), custom hiring stages, notification rules, and billing.
5. **Platform Super Administrators**: Overseeing global tenant health, subscription lifecycles, provider integrations, and security monitoring under strict audit controls.

---

## 2. Core Strategic Objectives

1. **Explainable AI Matching**: Move beyond black-box scoring to provide transparent, component-level candidate assessments grounded strictly in job descriptions and verifiable resume evidence.
2. **True Enterprise Multi-Tenancy**: Guarantee strict cryptographic and logical tenant isolation using shared PostgreSQL schemas guarded by application context and Row-Level Security (RLS).
3. **High-Performance Document Ingestion**: Process digital and scanned PDF resumes asynchronously with OCR fallback, preserving web responsiveness via Celery and Redis.
4. **Global Data Protection & Privacy**: Adhere to core privacy frameworks (GDPR, India DPDP, US employment privacy regulations) via explicit candidate consent, automated data retention rules, and self-service data export/erasure.
5. **Modular Monolithic Extensibility**: Build a cleanly bounded backend using FastAPI and Next.js, allowing rapid feature iteration while preserving future microservice extraction capabilities.

---

## 3. High-Level System Persona Requirements

### Persona A: Candidate (Job Seeker)
- **ID**: `PER-CAND`
- **Needs**: Transparent application status, resume version management, easy interview slot booking, and self-service privacy controls.
- **Key Pain Point**: Black-box rejections, clunky application forms, lack of interview rescheduling options, and inability to delete uploaded resumes.

### Persona B: Recruiter (Talent Acquisition Specialist)
- **ID**: `PER-REC`
- **Needs**: High-volume resume screening, automated skill extraction, candidate comparison matrices, customizable pipelines, and bulk communication.
- **Key Pain Point**: Manual screening fatigue, inconsistent candidate evaluations, and fragmented communication channels.

### Persona C: Hiring Manager (Departmental Lead)
- **ID**: `PER-HM`
- **Needs**: Scoped visibility into assigned requisitions only, structured scorecards, side-by-side candidate comparison, and collaborative note-taking.
- **Key Pain Point**: Overwhelming candidate volume, generic resumes, and unstructured interview feedback from interview panels.

### Persona D: Organization Admin (HR Operations / IT Lead)
- **ID**: `PER-ORG-ADM`
- **Needs**: User management, granular permission assignment, custom recruitment stage definitions, compliance audit logs, and billing visibility.
- **Key Pain Point**: Security vulnerabilities, lack of audit trails, rigid recruitment workflows, and cross-departmental data leaks.

### Persona E: Platform Super Admin (SaaS Operator)
- **ID**: `PER-PLAT-ADM`
- **Needs**: Tenant provisioning, subscription plan enforcement, AI provider cost tracking, dead-letter job queue monitoring, and global security telemetry.
- **Key Pain Point**: Unmonitored tenant resource exhaustion, uncontrolled LLM provider costs, and privileged account abuse risks.

---

## 4. Functional Requirements Matrix

| ID | Module / Domain | Requirement Description | Priority | Target Persona |
|:---|:---|:---|:---:|:---:|
| `FR-AUTH-01` | Authentication | Argon2id password-based login, email verification, password reset tokens, and HttpOnly session cookies. | P0 | All |
| `FR-AUTH-02` | Authentication | Optional Time-based One-Time Password (TOTP) Multi-Factor Authentication (MFA). | P1 | Recruiter, Admin |
| `FR-TEN-01` | Multi-Tenancy | Tenant context establishment via authenticated session, enforced at database session level via PostgreSQL RLS. | P0 | System |
| `FR-DOC-01` | Document Processing | Asynchronous PDF resume upload directly to private AWS S3 via expiring presigned URLs. | P0 | Candidate, Recruiter |
| `FR-DOC-02` | Document Processing | Two-tier text extraction (digital PDF parsing via `pdfplumber` with fallback to OCR engine for scanned files). | P0 | Recruiter, System |
| `FR-AI-01` | Skill Extraction | Taxonomy-driven canonical skill normalization (250+ skills) with alias resolution and semantic similarity matching. | P0 | Recruiter, System |
| `FR-AI-02` | Candidate Matching | Explainable scoring evaluating required skills (40%), experience (25%), qualifications (15%), preferred skills (10%), and role alignment (10%). | P0 | Recruiter, HM |
| `FR-AI-03` | Candidate Matching | Explicit prohibition of age, gender, race, or proxy demographic variables in all scoring formulas. | P0 | System |
| `FR-PIPE-01` | Recruitment Pipeline | Finite state machine enforcing validated stage transitions (`applied` $\rightarrow$ `shortlisted` $\rightarrow$ `interview_scheduled` $\rightarrow$ `interviewed` $\rightarrow$ `offered` $\rightarrow$ `hired` / `rejected`). | P0 | Recruiter, HM |
| `FR-INT-01` | Interviews | Multi-participant interview round scheduling, calendar invite generation (iCal/ICS), and conflict avoidance. | P1 | Recruiter, Candidate |
| `FR-INT-02` | Interviews | Structured scorecard submission with quantitative criteria and qualitative feedback notes. | P1 | HM, Recruiter |
| `FR-ASS-01` | Assessments | Rule-based and LLM-assisted interview question generation based on candidate skills, seniority tier, and job description. | P1 | Recruiter, HM |
| `FR-REP-01` | Reporting & Analytics| Recruiter dashboard metrics, stage conversion funnels, time-to-hire metrics, and asynchronous multi-sheet Excel/PDF exports. | P1 | Recruiter, Admin |
| `FR-PRIV-01` | Privacy & Compliance | Candidate self-service data export (JSON/ZIP) and right-to-be-forgotten deletion workflows. | P0 | Candidate, Admin |

---

## 5. Non-Functional Requirements (NFRs)

### Performance & Latency
- **NFR-PERF-01**: Web API endpoint $p95$ response time $\le 200\text{ ms}$ for standard transactional read/write operations.
- **NFR-PERF-02**: Resume document parsing, text extraction, and initial skill matching must complete asynchronously within $15\text{ seconds}$ for a standard 3-page digital PDF.
- **NFR-PERF-03**: Vector embedding search via `pgvector` must return top-50 candidate matches across $100,000$ records in $\le 100\text{ ms}$ using HNSW indexing.

### Reliability & Availability
- **NFR-REL-01**: SaaS platform availability target of **99.9%** uptime (excluding scheduled maintenance).
- **NFR-REL-02**: Celery background task processing must implement automatic retries with exponential backoff and dead-letter queues (DLQ) for failed operations.
- **NFR-REL-03**: Database backups: Point-in-Time Recovery (PITR) with 7-day retention and automated daily snapshots stored across multiple AWS Availability Zones.

### Security & Isolation
- **NFR-SEC-01**: Absolute tenant data isolation—zero cross-tenant data leakage via PostgreSQL Row-Level Security (RLS) and tenant-scoped repository patterns.
- **NFR-SEC-02**: Encryption in transit (TLS 1.3) and encryption at rest for all PostgreSQL databases, Redis caches, and S3 buckets using AWS KMS customer-managed keys.
- **NFR-SEC-03**: Strict Least-Privilege Access: Platform Super Admins must not have default read access to tenant resumes or candidate PII without logged, time-limited emergency access grants.

---

## 6. Assumptions & Scope Boundaries

### Approved Assumptions
1. **Initial Deployment Paradigm**: The platform starts as an **Asynchronous Modular Monolith** in FastAPI and Next.js, deployed on AWS ECS Fargate, PostgreSQL RDS, ElastiCache Redis, and S3.
2. **LLM Provider Strategy**: The platform will adopt a provider abstraction supporting OpenAI, Anthropic, and AWS Bedrock, selecting providers via tenant/platform configuration.
3. **Human-in-the-Loop AI**: AI scores and generated questions serve strictly as recommendations to recruiters and hiring managers; the system will never execute autonomous hiring or rejection decisions.

### Explicit Out-of-Scope Items for Initial Release
- Native mobile applications (iOS/Android); mobile access is handled via responsive web application.
- Autonomous AI voice/video interview conducting bots.
- Payroll and post-hire employee lifecycle management (HRIS / HRMS integrations are scheduled for future phases).
