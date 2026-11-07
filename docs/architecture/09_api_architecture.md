# API Architecture Specification

This document defines the REST API standards, URL conventions, pagination, error models, idempotency guarantees, and versioning strategy for the platform.

---

## 1. API Conventions & Standards

- **Base URI Path**: `/api/v1/`
- **Transport**: HTTPS (TLS 1.3) strictly required. HTTP requests are redirected to HTTPS at the Application Load Balancer.
- **Payload Format**: `application/json` (UTF-8) for standard endpoints; `multipart/form-data` strictly for presigned URL initiation.
- **Authentication**: Stateful HttpOnly session cookie (`aihr_access`) or `Authorization: Bearer <JWT>` header for machine-to-machine integrations.
- **Date/Time Formatting**: ISO 8601 strings in UTC (e.g. `2026-11-07T14:30:00Z`).

---

## 2. Standardized Error Response Model

All API error responses adhere strictly to the RFC 7807 (Problem Details for HTTP APIs) specification:

```json
{
  "type": "https://api.ai-hr.com/v1/errors/VALIDATION_ERROR",
  "title": "Validation Failed",
  "status": 422,
  "detail": "One or more fields failed schema validation rules.",
  "instance": "/api/v1/jobs",
  "code": "ERR_REQ_VALIDATION",
  "timestamp": "2026-11-07T14:30:00Z",
  "invalid_params": [
    {
      "name": "minimum_experience_years",
      "reason": "Must be a non-negative number."
    }
  ]
}
```

### Standard HTTP Status Codes:
- `200 OK`: Successful synchronous request.
- `201 Created`: Entity successfully created (returns `Location` header).
- `202 Accepted`: Long-running task accepted for asynchronous processing (returns job identifier).
- `204 No Content`: Successful request with no response body (e.g. DELETE).
- `400 Bad Request`: Malformed JSON or client request error.
- `401 Unauthorized`: Missing, expired, or invalid authentication credentials.
- `403 Forbidden`: Authenticated user lacks required permission or cross-tenant access attempted.
- `404 Not Found`: Target entity does not exist or belongs to another tenant (RLS filter).
- `409 Conflict`: Unique constraint violation (e.g. duplicate application to the same job).
- `422 Unprocessable Entity`: Pydantic schema validation failure.
- `429 Too Many Requests`: Rate limit exceeded.
- `500 Internal Server Error`: Unhandled server exception (tracked in CloudWatch/Sentry).

---

## 3. Pagination, Filtering, and Sorting

All collection endpoints (`GET /api/v1/...`) implement standard cursor-based or limit-offset pagination:

### Query Parameters:
- `page`: Integer page number (default: `1`, minimum: `1`).
- `page_size`: Integer items per page (default: `20`, maximum: `100`).
- `sort_by`: Field name to sort on (e.g. `applied_at`, `overall_match_score`).
- `sort_order`: `asc` or `desc` (default: `desc`).
- `filter[<field>]`: Structured filtering (e.g. `?filter[status]=published&filter[department_id]=uuid`).

### Standard Paginated Envelope:
```json
{
  "data": [ ... ],
  "pagination": {
    "current_page": 1,
    "page_size": 20,
    "total_items": 142,
    "total_pages": 8,
    "has_next": true,
    "has_prev": false
  }
}
```

---

## 4. Idempotency for Critical Operations

For financial or state-altering operations (e.g. bulk candidate transitions, interview slot booking, document upload initialization), endpoints support the `Idempotency-Key` header:
- Header: `Idempotency-Key: <UUIDv4>`
- Behavior:
  1. The API checks Redis for an active lock on `idempotency:{tenant_id}:{key}`.
  2. If the key exists and the previous request is complete, the cached response payload is immediately returned without re-executing business logic.
  3. If the key is currently processing, a `409 Conflict` is returned.
  4. Keys expire automatically after 24 hours.
