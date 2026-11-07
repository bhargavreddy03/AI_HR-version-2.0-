# System Acceptance Criteria & Definition of Done

This document defines the formal engineering acceptance criteria across each core functional domain, establishing objective gates for implementation sign-off.

---

## 1. Domain Acceptance Criteria Matrix

### Domain A: Multi-Tenancy & Security
- [ ] **AC-SEC-01**: PostgreSQL Row-Level Security (RLS) is enabled and enforced (`FORCE ROW LEVEL SECURITY`) on all tenant-scoped tables.
- [ ] **AC-SEC-02**: An authenticated user belonging to Tenant A querying any API endpoint with a Tenant B record identifier receives `404 Not Found`.
- [ ] **AC-SEC-03**: Password credentials are hashed exclusively using Argon2id with memory cost $\ge 64\text{ MB}$.
- [ ] **AC-SEC-04**: Session tokens are transmitted exclusively in `HttpOnly`, `Secure`, `SameSite=Lax` cookies; zero tokens stored in `localStorage` or `sessionStorage`.
- [ ] **AC-SEC-05**: Platform Super Admins cannot view tenant candidate dossiers or resumes without an explicit, time-limited, audited support grant.

### Domain B: Candidate & Document Management
- [ ] **AC-DOC-01**: Resume uploads stream directly from the browser to private S3 via presigned PUT URLs, with zero binary file buffering in web server memory.
- [ ] **AC-DOC-02**: File validation rejects files exceeding $15\text{ MB}$ or files whose magic bytes do not match `%PDF-`.
- [ ] **AC-DOC-03**: Scanned/image-only PDFs containing $<100$ characters automatically trigger Tier 2 OCR fallback (AWS Textract / Tesseract).
- [ ] **AC-DOC-04**: Candidates can download a full export of their personal profile and uploaded files in JSON/ZIP format within 60 seconds.
- [ ] **AC-DOC-05**: Candidate deletion requests execute an automated cascading delete across PostgreSQL and AWS S3 within 24 hours.

### Domain C: AI Screening & Candidate Matching
- [ ] **AC-AI-01**: The matching engine evaluates candidate alignment using the explainable multi-factor formula: Required Skills (40%), Experience (25%), Qualifications (15%), Preferred Skills (10%), and Semantic Alignment (10%).
- [ ] **AC-AI-02**: Every screening score displayed in the recruiter UI includes a component-level breakdown, missing required skills list, and verifiable resume evidence quotes.
- [ ] **AC-AI-03**: Zero demographic attributes (Age, Gender, Race, Nationality) are included in the feature vectors or matching formulas.
- [ ] **AC-AI-04**: Automated Disparate Impact testing confirms an adverse impact ratio $\ge 0.80$ across baseline cohorts.
- [ ] **AC-AI-05**: Vector similarity searches via `pgvector` return top-50 matches across $100,000$ documents in $\le 100\text{ ms}$.

### Domain D: Pipeline, Scheduling & Collaboration
- [ ] **AC-PIPE-01**: Candidate transitions strictly adhere to the finite state machine (`VALID_TRANSITIONS`), preventing invalid state leaps (e.g. `applied` directly to `hired`).
- [ ] **AC-PIPE-02**: Drag-and-drop Kanban updates execute optimistically on the client with automated rollback upon network failure.
- [ ] **AC-INT-01**: Interview booking automatically resolves interviewer panel conflicts and generates valid iCal (`.ics`) calendar attachments.
- [ ] **AC-INT-02**: Hiring managers can only view candidate records for requisitions where they are explicitly assigned as the hiring manager or panel reviewer.
- [ ] **AC-REP-01**: Multi-sheet Excel exports are generated asynchronously by Celery workers, notifying the user and delivering an expiring presigned S3 download link.
