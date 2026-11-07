# Step 2.1 — Architecture Technical Validation and Hardening Report

This report serves as the formal architectural sign-off and technical validation deliverable for **Step 2.1 — Architecture Validation, Database Correction and Security Hardening**.

---

## 1. Documentation Deliverables Reviewed

A technical review was conducted across all existing architecture documents in `docs/architecture/`, leading to targeted updates and new foundational specifications:

1. `04_multi_tenant_architecture.md`: **Completely Rewritten**. Corrected RLS transaction-local lifecycle, parameterized `set_config`, connection pool safety, role permissions, and concrete restrictive policies.
2. `05_database_design.md`: **Completely Hardened**. Corrected UUIDv7 strategy, replaced invalid timestamp functions, established composite tenant-safe foreign keys, and created dimension-safe embedding schemas.
3. `06_entity_relationships.md`: **Updated ERDs**. Synchronized sub-domain and high-level Mermaid diagrams with composite keys and entities.
4. `07_authentication_authorization.md`: **Hardened**. Resolved session cookie contradictions, established hybrid revocable session design, CSRF Double-Submit patterns, and organization switching protocols.
5. `CANDIDATE_IDENTITY_AND_PRIVACY.md`: **New Architecture Specification**. Formally separated global user identity, candidate personal profiles, tenant dossiers, and GDPR/DPDP export/erasure rules.
6. `FAIRNESS_AND_RESPONSIBLE_AI.md`: **New Architecture Specification**. Addressed proxy bias reality, defined separated fairness-audit store, and established small-sample-size statistical safeguards.
7. `CLOUD_AND_PROVIDER_VERIFICATION.md`: **New Architecture Specification**. Separated Multi-AZ HA from cross-region DR, removed unverified provider claims, and created deployment verification gates.
8. `MICROSERVICE_EXTRACTION_GUIDE.md`: **New Architecture Specification**. Detailed the 6 required distributed systems workstreams and refactoring investment required if future extraction is ever pursued.
9. `23_step_2_summary.md`: **Updated Summary**. Aligned architectural decisions, approved vs. open items, and readiness status.

---

## 2. Technical Inaccuracies Identified & Remediated

| Area | Initial Inaccuracy / Defect | Hardened Correction Completed |
|:---|:---|:---|
| **PostgreSQL RLS Lifecycle** | Used `SET LOCAL` during pool checkout hook; claimed RLS makes leakage "mathematically impossible". | Defined correct 8-step transaction-local lifecycle using parameterized `SELECT set_config('app.current_tenant_id', :id, true)` inside explicit `BEGIN` blocks; added pool reset listeners; noted RLS is defense-in-depth. |
| **RLS Policy Design** | Vague policy definitions; did not distinguish permissive vs. restrictive policies. | Defined valid, concrete `AS RESTRICTIVE` policies with `USING` and `WITH CHECK` clauses across SELECT, INSERT, UPDATE, DELETE for all 34 tenant tables. |
| **UUIDv7 Strategy** | Claimed UUIDv7 in text but specified `DEFAULT gen_random_uuid()` (which generates UUIDv4). | Standardized application-layer UUIDv7 generation using RFC 9562 libraries (`uuid-utils`) in SQLAlchemy model defaults, defining database columns as `UUID NOT NULL`. |
| **Invalid Timestamp Functions** | Used non-existent PostgreSQL function `clock_timestamp_real()`. | Replaced with standard valid PostgreSQL functions: `DEFAULT CURRENT_TIMESTAMP` or `DEFAULT clock_timestamp()`. |
| **Cross-Tenant Foreign Keys** | Simple foreign keys allowed potential cross-tenant referential leakage. | Enforced **composite tenant-safe foreign keys** (`FOREIGN KEY (tenant_id, parent_id) REFERENCES parent_table(tenant_id, id)`) on all child entities. |
| **Vector Dimension Lock-in** | Hardcoded fixed `vector(1536)` assumption, breaking compatibility with other models. | Designed multi-model dimension-safe architecture storing `model_identifier`, `vector_dimensions`, and dedicated typed columns (`embedding_1536`, `embedding_1024`, `embedding_768`). |
| **Authentication Contradiction**| Conflated stateless JWT cookies with stateful session cookies. | Designed hybrid revocable sessions: signed JWT access cookies ($15\text{ min}$) paired with sliding refresh tokens in Redis session registry for instant revocation. |
| **Organization Switching** | Did not specify re-authorization rules when switching tenants. | Mandated explicit switching endpoint requiring full membership verification and re-issuance of fresh tenant-scoped access tokens. |
| **Candidate Identity & Privacy** | Conflated global candidate user accounts with private employer recruitment notes. | Established 5-tier data separation: candidate profile data is never visible to other organizations; private interview notes remain strictly tenant-scoped. |
| **Fairness & 4/5ths Rule** | Implied 4/5ths ratio alone guarantees compliance; ignored demographic proxy variables. | Clarified proxy variable reality; created separated Fairness Audit store with restricted compliance access; added small-sample-size statistical safeguards. |
| **Cloud Provider Claims** | Claimed data always stays in VPC and all LLM providers guarantee zero retention. | Removed unverified claims; established explicit deployment verification requirements for Bedrock/OpenAI/Textract contracts and regional data residency. |
| **High Availability vs. DR** | Conflated Multi-AZ high availability with cross-region disaster recovery. | Explicitly distinguished Multi-AZ synchronous HA (RPO = 0, failover $\le 60\text{ s}$) from cross-region cold DR (RPO $\le 15\text{ min}$, RTO $\le 2\text{ hours}$). |
| **Microservice Extraction** | Claimed microservices could be extracted "without application rewrites". | Refactored guide explaining the 6 heavy workstreams required (DB splitting, Sagas, Kafka event bus, gRPC contracts, OpenTelemetry tracing). |

---

## 3. Remaining Open Strategic Decisions

1. **Primary LLM Provider Contract**: Formal selection of AWS Bedrock vs. Azure OpenAI vs. OpenAI Direct API for production tenant deployment.
2. **OCR Engine Selection**: Formal confirmation of AWS Textract vs. self-hosted Tesseract worker pool.
3. **Candidate Global Identity Linking**: Product confirmation on candidate multi-tenant portal experience.

---

## 4. Final Readiness Assessment for Step 2

- **Technical Rigor**: All PostgreSQL DDL patterns, RLS policies, composite foreign keys, session protocols, and AI governance workflows are implementation-ready and cross-reconciled.
- **Restrictions Maintained**: Zero application implementation code, migrations, tables, dependencies, or cloud infrastructure were created.
- **Status**: **STEP 2 AND STEP 2.1 ARE COMPLETE AND READY FOR STEP 3**.
