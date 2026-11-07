# Technical Debt Report

This document categorizes verified architectural, algorithmic, and engineering technical debt within the existing prototype, providing prioritized mitigation strategies for the target Modular Monolith SaaS.

---

## 1. High Priority (Must Resolve Before Production)

| Issue | Technical Root Cause | Impact | Recommended Mitigation |
|:---|:---|:---|:---|
| **No Authentication / Access Control** | `app.py` has no login, tenant context, or session tokens. | Anyone with URL access can view candidates, upload files, and trigger ML training. Zero compliance with GDPR, SOC 2, or enterprise privacy standards. | Implement `modules/auth` in FastAPI supporting OAuth2/OIDC, JWT session handling, and role-based access control (RBAC). |
| **No Durable Data Persistence** | State is held strictly in Streamlit `st.session_state`. | All pipeline states, uploaded candidates, and notes are lost on tab refresh or server restart. | Implement multi-tenant PostgreSQL with Row-Level Security (RLS) to durably store candidates, jobs, and pipeline records. |
| **ML Data Leakage (Pre-Split Transformations)** | `preprocessing.py:421-435` fits `SimpleImputer`, `PowerTransformer`, `RobustScaler`, and `VarianceThreshold` on the entire dataset prior to `train_test_split`. | Test partition leaks into training feature distributions; published model evaluation metrics suffer from optimistic bias. | Refactor into scikit-learn / imbalanced-learn `Pipeline`, fitting transformers strictly on training folds inside cross-validation. |
| **Latent Age-Penalty Formula** | `preprocessing.py:238` subtracts $0.25 \times \max(0, (\text{Age} - 45)/5)$. (Currently evaluates to 0 on the 21–45 dataset). | Introducing candidates $>45$ would trigger an active age penalty, causing severe legal liability under EEOC/ADEA. | Completely remove the age-penalty term and purge age/gender metadata from candidate screening feature matrices. |
| **Heavy In-Process ML / NLP Latency** | `skill_extractor.py:SemanticMatcher` imports `sentence-transformers` synchronously within the web request process. | Server worker threads block during model loading, causing timeouts and high memory spikes on web containers. | Offload vector embedding generation and semantic matching to asynchronous **Celery workers** with Redis, storing embeddings in **pgvector**. |

---

## 2. Medium Priority (Refactor During Service Migration)

| Issue | Technical Root Cause | Impact | Recommended Mitigation |
|:---|:---|:---|:---|
| **Hardcoded File System Paths** | Relative paths (`models/`, `static/graphs/`) hardcoded across modules. | Deployment fails in containerized multi-node environments or serverless containers. | Centralize configuration in Pydantic `BaseSettings` (`core/config.py`) driven by environment variables. |
| **Lack of Automated Test Suite** | Repository contains zero unit, integration, or regression tests. | High regression risk during domain refactoring and feature additions. | Introduce `pytest` suite with $\ge 80\%$ unit test coverage on core services (`skills`, `screening`, `pipeline`, `auth`). |
| **In-Memory Interview Scheduler** | `hr_agent.py:162-190` allocates static slots via an in-memory queue. | Double-booking occurs across concurrent sessions; no real calendar sync exists. | Re-architect as `modules/interviews` backed by PostgreSQL ACID transactions and Google/Outlook calendar webhooks. |
| **Duplicated Visualization Code** | `train_models.py:348-722` contains duplicated matplotlib/seaborn boilerplate across 16 plotting functions. | Maintenance friction and visual inconsistencies when modifying chart styles. | Consolidate plotting into modular chart generators or move to interactive client-side rendering (e.g. Recharts in Next.js). |

---

## 3. Low Priority (Code Quality & Hygiene)

| Issue | Technical Root Cause | Impact | Recommended Mitigation |
|:---|:---|:---|:---|
| **UI Styling Hardcoded in Python Strings** | `app.py:89-229` embeds 140 lines of CSS via `st.markdown(unsafe_allow_html=True)`. | Fragile frontend styling; tight coupling between styling and backend logic. | Replace completely with modern Tailwind CSS and component primitives in Next.js. |
| **Unused / Optional Imports** | `train_models.py` conditionally checks `xgboost`, `preprocessing.py` checks `imblearn`. | Potential dependency confusion and deployment bloat. | Pin exact package versions in Poetry / `pyproject.toml` with separate development and production dependency groups. |
| **Direct Console Logging** | `utils.py:175-179` prints unformatted logs to standard stdout. | Inability to filter by log levels or ingest into centralized logging (CloudWatch/Datadog). | Replace with structured JSON logging (`structlog` or standard `logging` configured with formatters). |

---

## Overall Assessment

The existing codebase contains well-designed core algorithmic concepts (taxonomy-driven skill extraction, deterministic scoring logic, and stateful hiring pipelines). However, it is an **academic/demo prototype** that lacks enterprise security, durable storage, and sound ML evaluation hygiene. Porting these core algorithms into the approved **Asynchronous Modular Monolith** architecture will resolve this technical debt while maintaining rapid developer velocity.
