# Risk Register

This document provides a comprehensive risk assessment for transitioning the AI HR prototype into an enterprise multi-tenant SaaS platform, detailing verified likelihoods, impacts, and architectural mitigations within the approved **Asynchronous Modular Monolith** framework.

---

## 1. Risk Register Matrix

| Risk ID | Risk Category | Risk Description | Likelihood | Impact | Mitigation Strategy within Target Architecture |
|:---:|:---|:---|:---:|:---:|:---|
| **R1** | **Security & Privacy** | **Zero Authentication & Access Control**: The prototype lacks authentication, authorization, or multi-tenant boundaries. Any user accessing the network port can view candidates and pipeline data. | **High** | **Critical** | Implement `modules/auth` in FastAPI using OAuth2/OIDC, JWT sessions (HttpOnly cookies), tenant context middleware, and PostgreSQL Row-Level Security (RLS). |
| **R2** | **Data Loss** | **Transient Memory Storage**: All candidate records, uploaded resumes, and pipeline updates reside in Streamlit's `st.session_state`. Refreshing the browser or restarting the container wipes all state. | **High** | **High** | Replace session state with durable PostgreSQL storage backed by automated backups, replication, and ACID transaction boundaries. |
| **R3** | **ML & Legal** | **Latent Age-Penalty Formula**: `preprocessing.py:238` subtracts $0.25 \times \max(0, (\text{Age} - 45)/5)$. While this currently evaluates to 0 on the 21–45 dataset, introducing candidates $>45$ would trigger active age penalties, violating EEOC / ADEA regulations. | **Medium** | **Critical** | Completely remove the age-penalty term. Strip age, graduation year, and gender from all scoring models and resume feature extractors. |
| **R4** | **Data Leakage & Model Validity** | **Pre-Split Data Leakage in ML Pipeline**: Imputers, power transformers, scalers, and variance selectors are fitted on the entire dataset prior to splitting (`preprocessing.py:421-435`). | **High** | **Medium** | Restructure the ML pipeline using scikit-learn / imbalanced-learn pipelines fitted strictly on training folds inside cross-validation. Retain the model primarily for analytics/benchmarking. |
| **R5** | **Performance & Scalability** | **Synchronous Heavy NLP / Embedding Latency**: Loading `sentence-transformers` or parsing large PDFs within the web request process blocks the event loop and exhausts server memory. | **High** | **High** | Offload all PDF text extraction, OCR, and embedding generation to **Celery background workers** via **Redis**, leaving FastAPI free to handle high-throughput I/O. |
| **R6** | **Calendar & State Conflicts** | **In-Memory Interview Scheduler**: The existing scheduler uses an in-memory queue (`_generate_available_slots`) without concurrency locks or external calendar synchronization. | **High** | **Medium** | Re-architect interview scheduling within `modules/interviews` using PostgreSQL transactional locks and two-way calendar sync (Google Calendar, Microsoft Graph). |
| **R7** | **Dataset Generalization** | **Synthetic Target Labels**: Candidate suitability labels are synthetically generated from a formula rather than verified real-world hiring outcomes. | **High** | **Medium** | Transition to transparent, explainable skill matching and vector similarity (`pgvector`) against job descriptions, combined with human-in-the-loop recruiter evaluations. |
| **R8** | **Document Parsing Brittleness** | **Scanned / Rasterized PDF Failures**: `extract_text_from_pdf()` relies on `pdfplumber` and `PyPDF2`, which cannot extract text from image-only scanned PDFs. | **Medium** | **Medium** | Add OCR fallback (e.g. AWS Textract or Tesseract) in the Celery document processing worker pipeline. |
| **R9** | **Regulatory Compliance (PII)** | **Plaintext Resume Storage**: Unencrypted resumes on local disk violate privacy compliance (GDPR, CCPA). | **Medium** | **High** | Store resumes in private **AWS S3** buckets with server-side encryption (SSE-KMS), generating short-lived pre-signed URLs for authorized recruiter access only. |
| **R10** | **Architectural Complexity** | **Premature Microservices Overhead**: Decomposing into independent microservices too early creates unnecessary networking complexity, distributed transaction overhead, and deployment friction. | **Medium** | **High** | Adopt an **Asynchronous Modular Monolith** as the initial approved architecture, enforcing clean domain boundaries that can be split into microservices only when justified by scale. |

---

## 2. Risk Mitigation Roadmap

1. **Phase 1 (Foundation)**: Establish multi-tenant database schemas with PostgreSQL RLS, JWT authentication middleware, and private S3 object storage.
2. **Phase 2 (Async Offloading)**: Deploy Redis and Celery worker pools to isolate PDF extraction, embedding calculations, and export builds from web request threads.
3. **Phase 3 (Algorithmic Governance)**: Eliminate all age-penalty logic, remove sensitive demographic features from candidate vectors, and utilize explainable vector matching via `pgvector`.
