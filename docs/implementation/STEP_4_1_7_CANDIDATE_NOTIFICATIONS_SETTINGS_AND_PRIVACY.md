# STEP 4.1.7 — CANDIDATE NOTIFICATIONS, SETTINGS AND PRIVACY

## Overview & Architecture Alignment

Step 4.1.7 completes the candidate account experience within the AI HR Intelligence Platform, fulfilling enterprise requirements for asynchronous candidate event notifications, honest email delivery telemetry, interview schedule visibility, full profile and security settings, and international data privacy (GDPR / CCPA / statutory recordkeeping compliance).

All components leverage the existing global candidate identity, Celery background workers, Redis message bus, and PostgreSQL 16 schema without duplicating existing subsystems.

---

## 1. Candidate Notification Center

### 1.1 Supported Candidate-Facing Events
- `email_verification`: Direct confirmation link generation and honest logging.
- `resume_processing_completion`: Asynchronous trigger upon completion of Step 3.10 document ingestion.
- `resume_processing_failure`: Alert on parsing/OCR errors with guidance to retry.
- `application_submission`: Instant immutable confirmation upon job application.
- `application_status_updates`: Stage transition alerts (e.g. under review, shortlisted).
- `interview_invitations`: Round scheduling notices with conference links.
- `interview_rescheduling` & `interview_cancellations`: Status change updates.
- `recruiter_communication`: Authorized recruiter notifications.

### 1.2 In-App Endpoints & IDOR Protection
- `GET /api/v1/candidates/me/notifications`: Paginated listing with optional `category` and `is_read` filters.
- `GET /api/v1/candidates/me/notifications/unread-count`: Fast aggregation query for sidebar/header badge counters.
- `PATCH /api/v1/candidates/me/notifications/{id}/read`: Strict single-record read transition verifying `notification.candidate_id == current_candidate.id` to prevent cross-candidate IDOR vulnerabilities.
- `POST /api/v1/candidates/me/notifications/read-all` & `POST /api/v1/candidates/me/notifications/mark-all-read`: Bulk updates for mark-all-read.

---

## 2. Asynchronous Email Integration & Honest Delivery Reporting

### 2.1 Celery Task & Idempotency
- **Worker Queue**: `notifications` queue in `app/modules/notifications/tasks.py`.
- **Task**: `dispatch_candidate_email_notification(notification_id, recipient_email, subject, body, idempotency_key)`.
- **Idempotency Key**: SHA-256 hash derived from `(notification_id, recipient_email, subject)` to prevent duplicate email transmissions during Celery task retries.

### 2.2 Honest Reporting Constraint
- When external SMTP or AWS SES infrastructure is not configured in environment settings, the platform explicitly logs:
  `"email_service_configured": False`
  and stores `"email_status": "unconfigured_environment"`.
- Never claims successful external transmission when mock or no-op handlers execute. Candidate in-app notifications remain fully functional and unblocked.

---

## 3. Interview Schedule Visibility

### 3.1 Architecture & Display Fields
- Reuses existing candidate application relationships via `GET /api/v1/candidates/me/interviews`.
- Real-time visibility into scheduled interview rounds:
  - Date & scheduled start timestamp.
  - Duration (minutes) and candidate's local timezone.
  - Interview type badge (`technical`, `behavioral`, `executive`, `screening`).
  - Meeting instructions and video conference link (`meeting_url`).
  - Authorized interviewer name and role.
  - Rescheduling notes and cancellation reasons.
- **Strict Constraint**: Zero fake records or synthetic interviews; clean empty state when no interviews are scheduled.

---

## 4. Account Settings & Security

### 4.1 Account & Personal Information
- `GET /api/v1/candidates/me/account`: Returns verified email, personal details, Argon2id password status, and last login IP.
- `PATCH /api/v1/candidates/me/account`: Updates first name, last name, phone number with input sanitization.
- `POST /api/v1/candidates/me/request-verification`: Dispatches email verification event with honest reporting.

### 4.2 Reauthentication & Password Changes
- `POST /api/v1/candidates/me/change-password`:
  - Enforces mandatory current password verification using Argon2id (`verify_password`).
  - Validates new password complexity (minimum 8 characters, upper/lower/numbers/special).
  - Updates password hash and revokes prior active candidate sessions.

### 4.3 Notification & Career Preferences
- **Notification Preferences**: Configurable flags for in-app alerts, email application updates, interview alerts, job matches, and digest frequency (`instant`, `daily`, `weekly`, `none`).
- **Career Preferences**: Desired job titles, preferred locations, remote preference (`remote`, `hybrid`, `onsite`, `flexible`), employment types (`full_time`, `contract`, etc.), and minimum salary with currency.

---

## 5. Privacy, Data Subject Rights & Statutory Compliance (GDPR / CCPA)

### 5.1 Personal Data Export (JSON)
- `GET /api/v1/candidates/me/privacy/export`: Generates a comprehensive, machine-readable JSON export of all candidate-submitted data:
  - Account and profile details.
  - Work experiences, education, certifications, projects, languages.
  - Uploaded resume metadata, SHA-256 hashes, and extracted skills.
  - Application history, questionnaires, and status timeline.
  - Consent history and IP addresses.
- **Trade Secret Disclaimer**: Explicitly documents that confidential recruiter evaluations, scorecards, and proprietary internal scoring algorithms are protected from applicant disclosure under trade secret and labor laws.

### 5.2 Formal Data Correction Requests
- `POST /api/v1/candidates/me/privacy/correction`: Registers formal correction requests logged in `candidate_privacy_requests` for manual review by data protection officers.

### 5.3 Account Erasure (Right to Be Forgotten) & Statutory Retention
- `POST /api/v1/candidates/me/privacy/delete`:
  - Requires mandatory password reauthentication.
  - Checks `user.litigation_hold`: If an active legal hold exists, erasure is strictly blocked with `ERR_LEGAL_HOLD_ACTIVE`.
  - Sets user account to inactive, deletes active sessions, and marks profile status as deleted.
  - **Statutory Retention Disclaimer**: In accordance with EEOC 29 C.F.R. § 1602, OFCCP 41 C.F.R. § 60-1.12, and GDPR Art. 17(3)(b), historical job applications, consent declarations, and immutable audit logs are retained for statutory compliance.
  - Interface explicitly disclaims: *“Do not claim legal compliance solely because these interfaces exist.”*

---

## 6. Database Migrations

- **Revision**: `006_candidate_settings_privacy`
- **Down Revision**: `005_app_submission`
- **Changes**:
  - Enhanced `candidate_notifications` table: added `event_type`, `payload` (JSONB), `email_sent` (Boolean), `email_status` (VARCHAR).
  - Enhanced `candidate_preferences` table: added `notification_preferences` (JSONB), `privacy_preferences` (JSONB).
  - Created `candidate_privacy_requests` table: `id`, `user_id`, `request_type`, `status`, `details`, `resolution_notes`, `created_at`, `updated_at`.

---

## 7. Verification Evidence

### Backend Pytest Results
- **Command**: `backend/.venv/Scripts/python.exe -m pytest backend/tests/test_candidate_portal.py -v`
- **Output**: 43 passed in 0.82s.
- **Regression Suite**: `test_candidate_portal.py`, `test_skill_registry.py`, `test_document_ingestion.py` — 126 passed out of 126.

### Frontend Vitest & TypeScript Results
- **Typecheck Command**: `npm.cmd --prefix frontend run typecheck` — 0 errors (Exit Code 0).
- **Vitest Command**: `npm.cmd --prefix frontend test -- --run` — 8 test files passed, 62 unit/component tests passed (Exit Code 0).
