# REST API Contracts Specification

This document provides representative REST API endpoint definitions, request schemas, response schemas, and error specifications across all core platform modules.

---

## 1. Authentication Domain

### `POST /api/v1/auth/login`
- **Purpose**: Authenticates a user with email and password; issues HttpOnly session cookies.
- **Required Permission**: Public / None.
- **Request Body**:
```json
{
  "email": "sarah.recruiter@acme-corp.com",
  "password": "SecurePassword123!",
  "organization_slug": "acme-corp"
}
```
- **Response (`200 OK`)**:
```json
{
  "user": {
    "id": "u1a2b3c4-d5e6-7f80-1234-56789abcdef0",
    "email": "sarah.recruiter@acme-corp.com",
    "first_name": "Sarah",
    "last_name": "Jenkins",
    "active_tenant_id": "t9a8b7c6-d5e4-3f21-0987-654321fedcba",
    "role": "recruiter",
    "permissions": ["jobs:create", "candidates:view_all", "screening:execute"]
  },
  "expires_in": 900
}
```

---

## 2. Jobs Domain

### `POST /api/v1/jobs`
- **Purpose**: Drafts a new job requisition within the tenant.
- **Required Permission**: `jobs:create`.
- **Request Body**:
```json
{
  "title": "Senior Cloud Infrastructure Engineer",
  "department_id": "d1a2b3c4-0000-0000-0000-000000000001",
  "hiring_manager_id": "u2a3b4c5-0000-0000-0000-000000000002",
  "location": "San Francisco, CA / Remote",
  "employment_type": "full_time",
  "workplace_type": "hybrid",
  "minimum_experience_years": 5.0,
  "description": "We are looking for an experienced AWS Cloud Engineer to scale our Kubernetes clusters...",
  "skills": [
    { "name": "AWS", "is_required": true, "importance_weight": 1.0 },
    { "name": "Kubernetes", "is_required": true, "importance_weight": 1.0 },
    { "name": "Terraform", "is_required": false, "importance_weight": 0.8 }
  ],
  "weights_config": {
    "required_skills": 0.40,
    "experience": 0.25,
    "qualifications": 0.15,
    "preferred_skills": 0.10,
    "alignment": 0.10
  }
}
```
- **Response (`201 Created`)**:
```json
{
  "id": "j9a8b7c6-1111-2222-3333-444455556666",
  "title": "Senior Cloud Infrastructure Engineer",
  "status": "draft",
  "slug": "senior-cloud-infrastructure-engineer",
  "created_at": "2026-11-07T14:40:00Z"
}
```

---

## 3. Documents & Resume Upload Domain

### `POST /api/v1/documents/resumes/upload-url`
- **Purpose**: Issues a private AWS S3 presigned PUT URL for client-side direct upload.
- **Required Permission**: `candidate:profile:manage` OR `candidates:view_all`.
- **Request Body**:
```json
{
  "candidate_id": "c1a2b3c4-5555-6666-7777-888899990000",
  "file_name": "alex_morgan_resume_2026.pdf",
  "file_size_bytes": 1420500,
  "mime_type": "application/pdf"
}
```
- **Response (`200 OK`)**:
```json
{
  "document_id": "doc12345-aaaa-bbbb-cccc-ddddeeeeffff",
  "upload_url": "https://ai-hr-resumes-prod.s3.amazonaws.com/tenants/t9a8b7c6.../guid.pdf?AWSAccessKeyId=...",
  "s3_key": "tenants/t9a8b7c6-d5e4-3f21-0987-654321fedcba/candidates/c1a2b3c4.../guid.pdf",
  "expires_in_seconds": 900
}
```

---

## 4. AI Screening Domain

### `POST /api/v1/screening/jobs/{job_id}/run`
- **Purpose**: Triggers an asynchronous explainable matching run across all applicants for a job.
- **Required Permission**: `screening:execute`.
- **Response (`202 Accepted`)**:
```json
{
  "screening_run_id": "sr-98765-aaaa-bbbb-cccc-111122223333",
  "job_id": "j9a8b7c6-1111-2222-3333-444455556666",
  "status": "queued",
  "estimated_duration_seconds": 12,
  "check_status_url": "/api/v1/screening/runs/sr-98765-aaaa-bbbb-cccc-111122223333"
}
```

### `GET /api/v1/screening/applications/{application_id}/result`
- **Purpose**: Fetches the detailed, explainable match breakdown for a candidate application.
- **Required Permission**: `candidates:view_assigned` OR `candidates:view_all`.
- **Response (`200 OK`)**:
```json
{
  "application_id": "app-0001-1111-2222-3333-444455556666",
  "candidate_name": "Alex Morgan",
  "overall_match_score": 0.8840,
  "component_scores": {
    "required_skills": 1.0000,
    "experience": 0.8500,
    "qualifications": 0.9000,
    "preferred_skills": 0.6000,
    "role_alignment": 0.8200
  },
  "skill_breakdown": {
    "matched_required": ["AWS", "Kubernetes", "Linux", "Docker"],
    "missing_required": [],
    "matched_preferred": ["Terraform"],
    "missing_preferred": ["Ansible"]
  },
  "explanation": "Candidate strongly matches all required infrastructure skills (AWS, Kubernetes). Total relevant experience (6.5 years) meets the 5-year requirement.",
  "evidence_excerpts": [
    {
      "skill": "Kubernetes",
      "excerpt": "Managed multi-tenant EKS production clusters across 4 AWS regions."
    }
  ],
  "model_version": "matching-engine-v2.1",
  "evaluated_at": "2026-11-07T14:45:00Z"
}
```

---

## 5. Pipeline & State Management Domain

### `POST /api/v1/pipeline/applications/{application_id}/transition`
- **Purpose**: Executes a validated hiring stage transition adhering to `VALID_TRANSITIONS`.
- **Required Permission**: `pipeline:transition`.
- **Request Body**:
```json
{
  "target_stage_id": "stage-tech-interview-uuid",
  "reason": "Passed recruiter screen; moving to technical round.",
  "send_notification_to_candidate": true
}
```
- **Response (`200 OK`)**:
```json
{
  "application_id": "app-0001-1111-2222-3333-444455556666",
  "previous_stage_id": "stage-screening-uuid",
  "current_stage_id": "stage-tech-interview-uuid",
  "status": "active",
  "updated_at": "2026-11-07T14:48:00Z"
}
```

---

## 6. Interview & Assessment Domain

### `POST /api/v1/assessments/generate-questions`
- **Purpose**: Generates role- and experience-aware interview questions.
- **Required Permission**: `candidates:view_assigned`.
- **Request Body**:
```json
{
  "skills": ["Kubernetes", "AWS", "Terraform"],
  "seniority_tier": "Senior",
  "experience_years": 6.5,
  "questions_per_skill": 2,
  "include_scenario_questions": true
}
```
- **Response (`200 OK`)**:
```json
{
  "questions": [
    {
      "id": "q-101",
      "skill": "Kubernetes",
      "type": "scenario",
      "difficulty": "hard",
      "question": "How would you diagnose and resolve a CrashLoopBackOff state caused by an OOMKilled container in a production pod?",
      "evaluation_criteria": [
        "Mentions kubectl describe pod and exit code 137",
        "Discusses adjusting memory requests/limits in resource spec",
        "Mentions inspecting container memory leak profiles"
      ]
    }
  ]
}
```
