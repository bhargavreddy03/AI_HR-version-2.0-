# Entity Relationship Diagrams (ERD)

This document provides visual domain-by-domain entity relationships and an overall system relationship model using Mermaid diagrams, reflecting composite tenant-safe foreign keys, typed embedding tables, and candidate global identity separation.

---

## 1. High-Level System Domain Relationship Model

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERSHIPS : employs
    ORGANIZATIONS ||--o{ DEPARTMENTS : contains
    ORGANIZATIONS ||--o{ JOBS : owns
    ORGANIZATIONS ||--o{ CANDIDATE_PROFILES : retains
    ORGANIZATIONS ||--o{ PIPELINE_TEMPLATES : configures

    USERS ||--o| CANDIDATE_USER_PROFILES : maintains
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : participates
    USERS ||--o{ CANDIDATE_PROFILES : optional_link
    ROLES ||--o{ ORGANIZATION_MEMBERSHIPS : assigns

    DEPARTMENTS ||--o{ JOBS : sponsors
    JOBS ||--o{ JOB_REQUIREMENTS : defines
    JOBS ||--o{ JOB_SKILLS : requires
    JOBS ||--o{ JOB_EMBEDDINGS : vectors
    JOBS ||--o{ APPLICATIONS : receives

    CANDIDATE_PROFILES ||--o{ CANDIDATE_DOCUMENTS : owns
    CANDIDATE_PROFILES ||--o{ RESUME_VERSIONS : tracks
    CANDIDATE_PROFILES ||--o{ CANDIDATE_SKILLS : possesses
    CANDIDATE_PROFILES ||--o{ APPLICATIONS : submits

    CANDIDATE_DOCUMENTS ||--o{ CANDIDATE_DOCUMENT_EMBEDDINGS : vectors

    APPLICATIONS ||--o{ SCREENING_RESULTS : scores
    SCREENING_RESULTS ||--o{ SCREENING_SCORE_COMPONENTS : details
    APPLICATIONS ||--o{ APPLICATION_STAGE_HISTORY : logs
    APPLICATIONS ||--o{ INTERVIEW_SCHEDULES : coordinates
    APPLICATIONS ||--o{ ASSESSMENTS : evaluates
    APPLICATIONS ||--o{ COMMENTS : discusses

    PIPELINE_TEMPLATES ||--o{ PIPELINE_STAGES : configures
    PIPELINE_STAGES ||--o{ APPLICATIONS : tracks

    INTERVIEW_SCHEDULES ||--o{ INTERVIEW_PARTICIPANTS : invites
    INTERVIEW_SCHEDULES ||--o{ INTERVIEW_SCORECARDS : records
    INTERVIEW_SCORECARDS ||--o{ INTERVIEW_FEEDBACK : notes
    ASSESSMENTS ||--o{ ASSESSMENT_QUESTIONS : contains
    ASSESSMENT_QUESTIONS ||--o{ ASSESSMENT_RESPONSES : receives
```

---

## 2. Detailed Sub-Domain ERDs (Enforcing Composite Foreign Keys)

### Sub-Domain A: Identity, Candidate Profiles & Tenancy
```mermaid
erDiagram
    USERS {
        uuid id PK
        varchar email UK
        varchar password_hash
        int token_version
        boolean is_active
        boolean is_super_admin
    }

    CANDIDATE_USER_PROFILES {
        uuid user_id PK, FK
        varchar headline
        text bio
        jsonb portfolio_urls
        jsonb self_declared_skills
    }

    ORGANIZATIONS {
        uuid id PK
        varchar name
        varchar slug UK
        varchar status
    }

    ORGANIZATION_MEMBERSHIPS {
        uuid id PK
        uuid tenant_id FK
        uuid user_id FK
        uuid role_id FK
        uuid department_id FK
        boolean is_active
    }

    CANDIDATE_PROFILES {
        uuid id PK
        uuid tenant_id PK, FK
        uuid user_id FK
        varchar first_name
        varchar last_name
        varchar email
        numeric total_experience_years
        boolean is_anonymized
    }

    USERS ||--o| CANDIDATE_USER_PROFILES : maintains
    USERS ||--o{ ORGANIZATION_MEMBERSHIPS : participates
    USERS ||--o{ CANDIDATE_PROFILES : optional_link
    ORGANIZATIONS ||--o{ ORGANIZATION_MEMBERSHIPS : employs
    ORGANIZATIONS ||--o{ CANDIDATE_PROFILES : retains
```

---

### Sub-Domain B: Documents, Typed Embeddings & Resumes
```mermaid
erDiagram
    CANDIDATE_PROFILES {
        uuid id PK
        uuid tenant_id PK, FK
        varchar email
    }

    CANDIDATE_DOCUMENTS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid candidate_id FK
        varchar s3_key
        varchar file_name
        varchar checksum_sha256
        text raw_text
    }

    EMBEDDING_MODELS {
        varchar model_identifier PK
        varchar provider
        int expected_dimensions UK
        boolean is_active
    }

    CANDIDATE_DOCUMENT_EMBEDDINGS {
        uuid id PK
        uuid tenant_id FK
        uuid document_id FK
        varchar model_identifier FK
        int vector_dimensions FK
        vector embedding_1536
        vector embedding_1024
        vector embedding_768
    }

    RESUME_VERSIONS {
        uuid id PK
        uuid tenant_id FK
        uuid candidate_id FK
        uuid document_id FK
        int version_number
        boolean is_primary
    }

    CANDIDATE_PROFILES ||--o{ CANDIDATE_DOCUMENTS : owns
    CANDIDATE_DOCUMENTS ||--o{ CANDIDATE_DOCUMENT_EMBEDDINGS : vectors
    EMBEDDING_MODELS ||--o{ CANDIDATE_DOCUMENT_EMBEDDINGS : constrains_dims
    CANDIDATE_PROFILES ||--o{ RESUME_VERSIONS : tracks
    CANDIDATE_DOCUMENTS ||--o{ RESUME_VERSIONS : references
```

---

### Sub-Domain C: Jobs, Typed Job Embeddings & Applications
```mermaid
erDiagram
    JOBS {
        uuid id PK
        uuid tenant_id PK, FK
        varchar title
        varchar status
        text description
        numeric minimum_experience_years
    }

    EMBEDDING_MODELS {
        varchar model_identifier PK
        varchar provider
        int expected_dimensions UK
        boolean is_active
    }

    JOB_EMBEDDINGS {
        uuid id PK
        uuid tenant_id FK
        uuid job_id FK
        varchar model_identifier FK
        int vector_dimensions FK
        vector embedding_1536
        vector embedding_1024
        vector embedding_768
    }

    PIPELINE_STAGES {
        uuid id PK
        uuid tenant_id PK, FK
        varchar name
        varchar stage_type
        int stage_order
    }

    APPLICATIONS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid job_id FK
        uuid candidate_id FK
        uuid resume_document_id FK
        uuid current_stage_id FK
        varchar status
        numeric overall_match_score
    }

    JOBS ||--o{ JOB_EMBEDDINGS : vectors
    EMBEDDING_MODELS ||--o{ JOB_EMBEDDINGS : constrains_dims
    JOBS ||--o{ APPLICATIONS : targets
    PIPELINE_STAGES ||--o{ APPLICATIONS : stages
```

---

### Sub-Domain D: AI Screening, Interviews & Assessments (Composite Keys Enforced)
```mermaid
erDiagram
    SCREENING_RUNS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid job_id FK
        timestamptz executed_at
    }

    SCREENING_RESULTS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid screening_run_id FK
        uuid application_id FK
        numeric overall_match_score
    }

    SCREENING_SCORE_COMPONENTS {
        uuid id PK
        uuid tenant_id FK
        uuid screening_result_id FK
        varchar component_name
        numeric score
    }

    INTERVIEW_SCHEDULES {
        uuid id PK
        uuid tenant_id PK, FK
        uuid application_id FK
        timestamptz start_time
    }

    INTERVIEW_SCORECARDS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid interview_id FK
        uuid interviewer_id FK
        varchar overall_recommendation
    }

    INTERVIEW_FEEDBACK {
        uuid id PK
        uuid tenant_id FK
        uuid scorecard_id FK
        text feedback_notes
    }

    ASSESSMENTS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid application_id FK
    }

    ASSESSMENT_QUESTIONS {
        uuid id PK
        uuid tenant_id PK, FK
        uuid assessment_id FK
        text question_text
    }

    ASSESSMENT_RESPONSES {
        uuid id PK
        uuid tenant_id FK
        uuid question_id FK
        text candidate_response
    }

    SCREENING_RUNS ||--o{ SCREENING_RESULTS : yields
    SCREENING_RESULTS ||--o{ SCREENING_SCORE_COMPONENTS : composite_details
    INTERVIEW_SCHEDULES ||--o{ INTERVIEW_SCORECARDS : records
    INTERVIEW_SCORECARDS ||--o{ INTERVIEW_FEEDBACK : composite_notes
    ASSESSMENTS ||--o{ ASSESSMENT_QUESTIONS : contains
    ASSESSMENT_QUESTIONS ||--o{ ASSESSMENT_RESPONSES : composite_answers
```
