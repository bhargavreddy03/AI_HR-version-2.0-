# Step 2 Architecture & Blueprint Summary

## 1. Executive Summary

This document provides the consolidated architectural summary for **Step 2 and Step 2.1 — System Architecture, Blueprint and Validation** for the enterprise AI HR Intelligence and Applicant Tracking System (ATS) SaaS platform.

Following the initial Step 2 design and subsequent technical hardening in Step 2.1, all architectural blueprints, database schemas, security models, and governance frameworks have been rigorously verified and reconciled.

### Strict Design-Only Rule Compliance:
- **No application code was created or modified**.
- **No database migrations or tables were executed**.
- **No dependencies or packages were installed**.
- **No cloud infrastructure was provisioned**.
- All deliverables reside strictly as Markdown and Mermaid architecture documents inside `docs/architecture/`.

---

## 2. Hardened Architectural Baseline

1. **Architecture Style**: **Asynchronous Modular Monolith**. FastAPI backend structured into strict domain modules (`auth`, `organizations`, `candidates`, `jobs`, `screening`, `pipeline`, `interviews`, `assessments`, `documents`, `reporting`) deployed on AWS ECS Fargate, paired with Next.js 14 on the frontend.
2. **PostgreSQL Multi-Tenancy (Hardened)**:
   - Shared database, shared schema with composite tenant-safe foreign keys.
   - Transaction-local tenant parameter setting using parameterized `SELECT set_config('app.current_tenant_id', :tenant_id, true)` inside explicit `async with session.begin():` blocks.
   - PostgreSQL Row-Level Security (RLS) policies (`FORCE ROW LEVEL SECURITY`, `AS RESTRICTIVE`) applied across all 33 tenant-scoped tables, complemented by 10 platform-global tables (43 relational tables total).
3. **Database & Schema Standards**:
   - Primary keys generated as **UUIDv7** at the application layer via RFC 9562 libraries.
   - Valid standard timestamp functions (`DEFAULT CURRENT_TIMESTAMP` or `clock_timestamp()`).
   - Dimension-safe vector embeddings table supporting variable vector dimensions (`1536`, `1024`, `768`) indexed with HNSW.
4. **Authentication & Session Consistency**:
   - Hybrid revocable sessions: Signed JWT access tokens ($15\text{ min}$) paired with sliding refresh tokens ($7\text{ days}$) stored in **HttpOnly, Secure, SameSite=Lax/Strict** cookies.
   - Instant revocation tracking via Redis session registry; Double-Submit Cookie CSRF defense on state-altering requests.
   - Organization switching requiring fresh membership validation and token re-issuance.
5. **Responsible AI & Candidate Privacy**:
   - Explainable multi-factor scoring with zero demographic attributes (age, gender, ethnicity strictly excluded).
   - Separated Fairness Audit store for compliance officer analysis, incorporating small-sample-size statistical safeguards.
   - Complete candidate privacy rights: explicit consent, self-service data export, right-to-be-forgotten anonymization/erasure.
6. **Cloud & High Availability Guarantees**:
   - Clear distinction between AWS Multi-AZ High Availability (synchronous RDS failover in $\le 60\text{ s}$, RPO = 0) and cross-region disaster recovery (RPO $\le 15\text{ min}$, RTO $\le 2\text{ hours}$).
   - Explicit deployment verification requirements for cloud LLM and OCR providers.

---

## 3. Approved vs. Recommended vs. Open Decisions

### Approved Decisions:
- **Architecture**: Asynchronous Modular Monolith (FastAPI + Next.js 14).
- **Multi-Tenancy**: Shared database, shared schema with PostgreSQL Restrictive RLS.
- **Identifier Strategy**: Application-generated UUIDv7 primary keys.
- **AI Matching**: Explainable weighted multi-factor scoring with pgvector semantic similarity.
- **Session Architecture**: Hybrid revocable sessions via HttpOnly cookies and Redis registry.

### Recommended Decisions:
- **Primary Production LLM**: AWS Bedrock (Claude 3.5 Sonnet / Haiku) for VPC boundary security and zero customer data retention.
- **Primary Production OCR**: AWS Textract for scanned PDF fallback.

### Open Decisions for Step 3 Alignment:
1. **Candidate Global Identity**: Final product sign-off on global `users` authentication linking to tenant-scoped `candidate_profiles` dossiers.
2. **Secondary Cloud Region**: Selection of secondary AWS disaster recovery region (e.g. `us-east-1` primary, `us-west-2` DR).

---

## 4. Formal Readiness Declaration

All documentation files have been updated, cross-referenced, and verified for complete architectural consistency.

**STEP 2 AND STEP 2.1 ARE COMPLETE.**
No implementation code has been written. Awaiting your formal review and approval before proceeding to Step 3.
