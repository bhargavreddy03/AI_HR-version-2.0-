# Security, Privacy and Global Regulatory Compliance

This document establishes the security controls, data classification standards, encryption mechanisms, candidate privacy rights, and multi-jurisdiction compliance framework.

---

## 1. Data Classification & Protection Matrix

| Data Classification Tier | Examples | Storage Location | Encryption at Rest | Access Policy | Retention Period |
|:---|:---|:---|:---|:---|:---|
| **Tier 1: Highly Sensitive / Auth Credentials** | Password hashes, MFA secrets, API keys, JWT signing keys | PostgreSQL (`users`), AWS Secrets Manager | Argon2id / AES-256-GCM / AWS KMS | Application security layer only; never exposed via API | Active session lifecycle + 30 days revocation |
| **Tier 2: Candidate PII & Resumes** | Full name, email, phone, location, PDF resume bytes, work history | S3 (`resumes/`), PostgreSQL (`candidate_profiles`) | AWS KMS SSE-S3 / AES-256 | Tenant RBAC + Signed URLs (15 min expiry) | Candidate consent duration (e.g. 1–2 yrs or on-demand erasure) |
| **Tier 3: Recruitment & Scoring Data** | Job descriptions, screening scores, interview scorecards, notes | PostgreSQL (`jobs`, `screening_results`, `applications`) | AWS RDS KMS Encrypted Storage | Tenant RBAC + Assigned HM Scoping | 3–7 years based on corporate retention policy |
| **Tier 4: System Audit Logs** | Administrative logins, export events, RLS policy violation attempts | PostgreSQL (`platform_audit_logs`), AWS CloudWatch | AWS RDS KMS / CloudWatch KMS | Immutable / Read-only for compliance auditors | 7 years (Statutory compliance requirement) |

---

## 2. Global Privacy & Jurisdiction-Aware Compliance Framework

The platform is designed to operate globally across multiple legal jurisdictions. The table below outlines key regulatory requirements and technical enforcement mechanisms:

| Jurisdiction / Regulation | Core Legal Mandate | Technical Enforcement in Platform Architecture |
|:---|:---|:---|
| **European Union: GDPR** (General Data Protection Regulation) | Right of Access, Right to Rectification, Right to Erasure (*Right to be Forgotten*), Purpose Limitation. | Candidate self-service JSON data export; automated cascade deletion removing candidate records from DB and S3. |
| **India: Digital Personal Data Protection Act (DPDP 2023)** | Clear notice, unconditional consent withdrawal, data principal rights, reasonable security safeguards. | Explicit consent checkmark at job application; candidate privacy portal with real-time consent revocation toggles. |
| **United States: EEOC & Title VII** (Equal Employment Opportunity) | Prohibition of employment discrimination based on race, color, religion, sex, national origin, or age (ADEA). | Total exclusion of demographic attributes from matching formulas; automated 4/5ths disparate impact testing. |
| **United States: NYC Local Law 144** (Automated Employment Decision Tools) | Mandatory annual independent bias audits of automated recruitment tools; published summary of results. | Explainable component-level scoring models; immutable screening logs supporting third-party bias auditing. |

> **Important Legal Disclaimer**: This document specifies technical architectural controls designed to support data privacy and security compliance. It does not constitute formal legal counsel. Enterprise customers must conduct independent legal reviews with qualified counsel regarding jurisdiction-specific employment and data privacy obligations.
