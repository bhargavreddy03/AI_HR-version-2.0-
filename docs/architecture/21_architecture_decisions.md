# Architectural Decision Records (ADR)

This document formalizes the key strategic architectural decisions made for the platform, documenting the context, alternatives considered, chosen rationale, and consequences.

---

## ADR-001: Architectural Style — Asynchronous Modular Monolith vs. Microservices

### Context:
We are building a commercial enterprise recruitment SaaS from an existing Streamlit prototype. We must determine whether to architect the backend as distributed microservices or as a modular monolith.

### Alternatives Considered:
1. **Independent Microservices**: Distributed services (Auth Service, Screening Service, Document Service, etc.) deployed as independent containers with independent databases.
2. **Asynchronous Modular Monolith**: A single deployable FastAPI backend structured into strict domain modules with separate repositories and services, combined with Celery background workers and shared PostgreSQL with pgvector.

### Decision:
Adopt the **Asynchronous Modular Monolith**.

### Rationale:
- **Operational Simplicity**: Avoids premature distributed systems overhead (network serialization latency, service discovery, distributed tracing, complex multi-repo CI/CD).
- **ACID Transaction Guarantees**: Allows atomic cross-domain state management within a single database transaction, avoiding distributed Saga failure edge-cases.
- **Future Extraction Readiness**: Enforcing strict domain write boundaries and service encapsulation allows any single high-load module to be extracted into a standalone service in the future if scale warrants it.

---

## ADR-002: Multi-Tenancy Baseline — Shared Schema with RLS vs. Schema-per-Tenant

### Context:
The SaaS platform must support hundreds of organizations with complete data isolation and cost-effective database scaling.

### Alternatives Considered:
1. **Database-per-Tenant**: Separate physical PostgreSQL database per customer.
2. **Schema-per-Tenant**: Single database with separate PostgreSQL schemas (`org_123.applications`).
3. **Shared Database, Shared Schema with PostgreSQL Row-Level Security (RLS)**: Single shared schema with `tenant_id` columns guarded by RLS policies.

### Decision:
Adopt **Shared Database, Shared Schema with PostgreSQL Row-Level Security (RLS)**.

### Rationale:
- **Migration Scalability**: Schema-per-tenant requires executing hundreds of DDL migrations on every release, leading to migration drift and high operational risk.
- **Connection Efficiency**: A shared schema maximizes connection pool utilization via PgBouncer / RDS Proxy.
- **Defense in Depth**: Combining application-level repository scoping with engine-level RLS policies guarantees that even buggy queries cannot leak cross-tenant data.

---

## ADR-003: Candidate-Job Matching Paradigm — Explainable Scoring vs. Black-Box Neural Ranking

### Context:
The existing prototype contained a synthetic machine learning model trained on flawed data. We must define the primary candidate screening engine for production.

### Alternatives Considered:
1. **Supervised Black-Box Deep Learning Ranking**: Training a neural network to rank resumes directly based on past hiring outcomes.
2. **Explainable Multi-Factor Scoring with Semantic Vectors (`pgvector`)**: Combining deterministic skill coverage, experience ratios, and qualifications with cosine semantic vector similarity.

### Decision:
Adopt **Explainable Multi-Factor Scoring with Semantic Vectors (`pgvector`)**.

### Rationale:
- **Regulatory Compliance**: Legal mandates (e.g. NYC Local Law 144, EU AI Act, EEOC Title VII) require transparent, auditable justification for automated recruitment tools. Black-box neural models present unacceptable regulatory and legal liabilities.
- **Recruiter Trust**: Hiring teams demand to know *why* a candidate received a score (e.g. *"Missing 2 required skills: Kubernetes, AWS"*).
- **Immediate Data Viability**: Avoids dependence on scarce, clean historical hiring outcome datasets.
