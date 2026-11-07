# System Architecture Blueprint

## 1. Architectural Paradigm: Asynchronous Modular Monolith

The **AI HR Platform** is architected as an **Asynchronous Modular Monolith**. 

This paradigm combines the simplicity, atomic deployment, and single-codebase developer velocity of a monolith with the strict domain boundaries, asynchronous performance offloading, and eventual microservice readiness required for enterprise commercial scale.

```mermaid
graph TB
    subgraph ClientTier ["Client Presentation Layer (Next.js 14)"]
        WebSPA["Next.js App Router (React, TypeScript, Tailwind, shadcn/ui)"]
        StateMgt["TanStack Query (Client Cache) & React Hook Form + Zod"]
    end

    subgraph GatewayTier ["Ingress & Security Layer"]
        WAF["AWS WAF (DDoS, Rate Limiting, OWASP Top 10)"]
        ALB["Application Load Balancer (HTTPS Termination, Health Checks)"]
    end

    subgraph MonolithCore ["FastAPI Backend (Modular Monolith Core)"]
        FastAPI_App["FastAPI Master Application"]
        MiddlewareStack["Middleware: CORS, GZip, Tenant Context, Audit Logging"]
        
        subgraph DomainModules ["Strict Domain Modules (Service & Repository Pattern)"]
            AuthMod["modules/auth"]
            TenantMod["modules/organizations"]
            CandMod["modules/candidates"]
            JobMod["modules/jobs"]
            ScreenMod["modules/screening"]
            PipeMod["modules/pipeline"]
            IntMod["modules/interviews"]
            AssessMod["modules/assessments"]
            DocMod["modules/documents"]
            ReportMod["modules/reporting"]
        end
    end

    subgraph AsyncTier ["Asynchronous Compute & Task Layer"]
        RedisBroker[("ElastiCache Redis<br/>(Task Broker & Response Cache)")]
        CeleryPool["Celery Worker Fleet (ECS Fargate)<br/>• Document Ingestion & Text Extraction<br/>• OCR Fallback Processing<br/>• pgvector Embedding Generation<br/>• Batch Screening & Ranking Runs<br/>• Email & Notification Dispatch<br/>• Asynchronous Excel/PDF Reports"]
    end

    subgraph StorageTier ["Data & Object Persistence Layer"]
        PostgresDB[("AWS RDS PostgreSQL 16 Multi-AZ<br/>• pgvector Vector Extension (HNSW Indexing)<br/>• Row-Level Security (RLS) Multi-Tenant Policies<br/>• Relational Integrity & ACID Transactions")]
        S3Bucket[("Private AWS S3 Object Storage<br/>• Customer Resumes (KMS SSE-S3)<br/>• Presigned Upload/Download URLs<br/>• Generated Report Archives")]
    end

    WebSPA --> WAF --> ALB --> FastAPI_App
    FastAPI_App --> MiddlewareStack
    MiddlewareStack --> DomainModules

    DomainModules --> PostgresDB
    DomainModules --> RedisBroker
    DomainModules --> S3Bucket

    RedisBroker --> CeleryPool
    CeleryPool --> PostgresDB
    CeleryPool --> S3Bucket
    CeleryPool --> RedisBroker
```

---

## 2. Domain Module Decomposition & Isolation Rules

The FastAPI backend is strictly structured around domain packages located under `backend/app/modules/`. Each module is self-contained with its own models, schemas, repositories, and domain services:

```
backend/app/modules/
├── auth/                 # Identity, credentials, sessions, MFA, JWT issuance
├── organizations/        # Tenants, departments, teams, subscription tracking
├── candidates/           # Candidate dossiers, experience, education, skills
├── jobs/                 # Requisitions, job posts, hiring criteria, weights
├── screening/            # Explainable matching engine, pgvector embeddings
├── pipeline/             # FSM hiring stages, transitions, state history
├── interviews/           # Slot booking, panel coordination, scorecards
├── assessments/          # Rule-based & LLM question generator, response evaluation
├── documents/            # S3 presigned URL issuance, document validation
├── reporting/            # Metrics aggregation, Excel/PDF background exports
└── audit/                # Immutable platform and organization audit logs
```

### Module Boundary Governance Rules:
1. **Strict Write Ownership**: Each domain module strictly owns its respective database tables. A domain module is **never permitted** to perform direct `INSERT`, `UPDATE`, or `DELETE` statements on tables owned by another domain. State mutations must occur via public method calls on the owning domain's `Service` class.
2. **Controlled Read Projections**: Cross-domain read access is permitted through controlled Service queries or optimized read-only repository projections to avoid excessive in-process joins or performance bottlenecks on complex dashboard views.
3. **Dependency Injection**: Services and repositories are resolved using FastAPI's dependency injection (`Depends()`), ensuring clear unit-testability and mocking.
4. **Asynchronous Delegation**: Any operation exceeding $50\text{ ms}$ of CPU or network time (e.g. PDF parsing, OCR, vector embedding generation, LLM completion calls, bulk report generation) must be dispatched as a background Celery task.

---

## 3. Data & Asynchronous Execution Flow

### High-Throughput Resume Ingestion Workflow:
```mermaid
sequenceDiagram
    autonumber
    participant Browser as Next.js Client
    participant API as FastAPI (Document Module)
    participant S3 as Private AWS S3
    participant Redis as Redis Queue
    participant Worker as Celery Worker
    participant DB as PostgreSQL (pgvector & RLS)

    Browser->>API: POST /api/v1/documents/resumes/upload-url (fileName, fileSize, mimeType)
    API->>API: Validate file type (PDF only), size (<= 15MB), and tenant quota
    API->>S3: Generate S3 Presigned PUT URL with KMS encryption metadata
    API-->>Browser: { uploadUrl, documentId, s3Key, expiresAt }
    
    Browser->>S3: Direct PUT binary payload to S3 Presigned URL
    S3-->>Browser: 200 OK (ETag)

    Browser->>API: POST /api/v1/documents/resumes/{documentId}/confirm-upload
    API->>DB: INSERT candidate_documents (status = 'uploaded', s3_key)
    API->>Redis: Enqueue process_resume_document(document_id, tenant_id)
    API-->>Browser: 202 Accepted { documentId, status: 'queued' }

    Redis->>Worker: Consume process_resume_document
    Worker->>S3: Download resume bytes from S3
    Worker->>Worker: Tier 1 Text Extraction (pdfplumber)
    alt Text Extraction Empty / Scanned
        Worker->>Worker: Tier 2 OCR Fallback (Textract / Tesseract)
    end
    Worker->>Worker: SkillExtractor.extract() (Taxonomy & Aliases)
    Worker->>Worker: Generate vector embedding (pgvector compatible)
    Worker->>DB: UPDATE candidate_documents & INSERT candidate_skills, embeddings
    Worker->>Redis: Publish SSE/WebSocket event: "DOCUMENT_PROCESSED"
    Redis-->>Browser: Push Real-Time Toast: "Resume parsed successfully"
```

---

## 4. Architectural Readiness for Future Service Extraction

The platform avoids the operational overhead of microservices today (service meshes, distributed tracing, network latency, distributed transactions). However, should specific modules experience extreme horizontal scaling demands in the future (e.g. `screening` vector search or `documents` OCR parsing), the architecture supports clean extraction:

1. **Clean Service Interfaces**: Because external modules only interact with a domain via its public Service API, replacing in-process method calls with an HTTP/gRPC client requires minimal refactoring.
2. **Explicit Database Ownership**: Because tables are grouped strictly by domain ownership, migrating a module's tables to a dedicated database schema or cluster is straightforward.
3. **Event Broker Evolution**: In-process domain event dispatchers can be swapped for an external message bus (e.g. Apache Kafka or AWS SQS/SNS) with zero impact on core business logic.
