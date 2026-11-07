# Development Dependencies

This document provides a preliminary inventory of Python libraries observed in the prototype source code, alongside anticipated dependencies for the target Asynchronous Modular Monolith SaaS.

> **Important Notice on Versions**: All package versions listed below are **preliminary and indicative**. They represent typical historical release baselines rather than final, production-approved, or locked dependencies. Exact version pinning will be established via Poetry / `pyproject.toml` or `requirements.txt` during the initial setup of Step 2 following security audits and environment compatibility checks.

---

## 1. Prototype Dependencies (Observed in Source Code)

The following libraries are imported directly across `app.py`, `preprocessing.py`, `train_models.py`, `skill_extractor.py`, `question_generator.py`, and `utils.py`:

| Package | Imported In | Primary Responsibility | Preliminary Baseline Version |
|:---|:---|:---|:---:|
| **streamlit** | `app.py` | Dashboard UI and session state management | `~=1.30.0` (Preliminary) |
| **pandas** | `utils.py`, `preprocessing.py`, `train_models.py`, `app.py` | In-memory candidate data frames and table transformations | `~=2.2.0` (Preliminary) |
| **numpy** | `preprocessing.py`, `train_models.py`, `hr_agent.py` | Vector operations, array manipulation, and random number generation | `~=1.26.0` (Preliminary) |
| **scikit-learn** | `preprocessing.py`, `train_models.py`, `hr_agent.py` | TF-IDF vectorization, feature scaling, imputation, and baseline classifiers | `~=1.4.0` (Preliminary) |
| **imbalanced-learn** | `preprocessing.py` | SMOTE over-sampling implementation | `~=0.12.0` (Preliminary) |
| **joblib** | `train_models.py`, `hr_agent.py`, `preprocessing.py` | Serialization of models and preprocessor pipelines | `~=1.3.0` (Preliminary) |
| **xgboost** | `train_models.py` (optional) | Gradient boosted decision tree classifier | `~=2.0.0` (Preliminary) |
| **matplotlib** | `train_models.py`, `app.py` | Generation of 16 evaluation metric comparison charts | `~=3.8.0` (Preliminary) |
| **seaborn** | `train_models.py` | Confusion matrix heatmaps and dark-theme aesthetics | `~=0.13.0` (Preliminary) |
| **pdfplumber** | `app.py` | Primary PDF resume text extraction engine | `~=0.10.0` (Preliminary) |
| **PyPDF2** | `app.py` | Fallback PDF text extraction engine | `~=3.0.0` (Preliminary) |
| **openpyxl** | `app.py` | Multi-sheet Excel workbook export generation (`.xlsx`) | `~=3.1.0` (Preliminary) |
| **sentence-transformers** | `skill_extractor.py` (optional) | Semantic embeddings for skill matching (guarded by flag) | `~=2.2.2` (Preliminary) |
| **torch** | `skill_extractor.py` (optional backend) | Deep learning runtime supporting sentence-transformers | `~=2.2.0` (Preliminary) |
| **Standard Library** | Various modules | `os`, `sys`, `re`, `json`, `io`, `csv`, `random`, `datetime`, `dataclasses`, `typing` | Built-in (Python 3.11+) |

---

## 2. Anticipated Dependencies for Target Modular Monolith SaaS

During the upcoming architecture implementation, the following preliminary dependencies will be evaluated for the FastAPI backend and Celery worker ecosystem:

| Target Domain | Anticipated Library | Architectural Purpose |
|:---|:---|:---|
| **API Framework** | `fastapi`, `uvicorn[standard]` | High-performance asynchronous REST API framework |
| **Data Validation** | `pydantic`, `pydantic-settings` | Request/response DTO schemas and environment configuration |
| **Database & ORM** | `sqlalchemy[asyncio]`, `asyncpg` | Async PostgreSQL driver and object-relational mapping |
| **Database Migrations**| `alembic` | Versioned schema migration management |
| **Vector Search** | `pgvector` | Python bindings for PostgreSQL vector similarity indexing |
| **Background Tasks** | `celery`, `redis` | Asynchronous task queue and worker management |
| **Object Storage** | `boto3`, `aioboto3` | Encrypted AWS S3 client for private PDF resume storage |
| **Security & Auth** | `python-jose[cryptography]`, `passlib[bcrypt]` | JWT token encode/decode and password hashing |
| **Testing & Quality** | `pytest`, `pytest-asyncio`, `httpx` | Automated unit, integration, and API testing suite |

*Note: Final dependency locking and vulnerability scanning will occur during Step 2 repository scaffolding.*
