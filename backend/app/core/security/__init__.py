"""Enterprise security foundation package for AI HR Intelligence Platform."""

from app.core.security.ai_security import (
    AIRecommendationEnvelope,
    AISecurityException,
    build_safe_llm_prompt,
    detect_prompt_injection_indicators,
    sanitize_untrusted_text,
    wrap_advisory_recommendation,
)
from app.core.security.audit import (
    SecurityAuditEvent,
    log_security_event,
    sanitize_audit_details,
    sanitize_audit_value,
)
from app.core.security.context import (
    SecurityContext,
    TenantContext,
    get_security_context,
    get_tenant_context,
    set_tenant_context,
)
from app.core.security.encryption import (
    decrypt_sensitive_data,
    derive_field_encryption_key,
    encrypt_sensitive_data,
)
from app.core.security.file_security import (
    BaseMalwareScanner,
    FileSecurityException,
    MalwareScanResult,
    NullMalwareScanner,
    get_malware_scanner,
    set_malware_scanner,
    validate_document_upload,
)
from app.core.security.hasher import (
    get_password_hasher,
    hash_password,
    needs_rehash,
    verify_password,
)
from app.core.security.headers import (
    DEFAULT_CSP_POLICY,
    SecurityHeadersMiddleware,
)
from app.core.security.password import (
    PasswordPolicyException,
    validate_password_complexity,
)
from app.core.security.rate_limit import (
    check_rate_limit,
    rate_limit,
)
from app.core.security.rbac import (
    ROLE_CANDIDATE,
    ROLE_HIRING_MANAGER,
    ROLE_ORG_ADMIN,
    ROLE_PLATFORM_SUPER_ADMIN,
    ROLE_RECRUITER,
    assert_tenant_ownership,
    assert_user_ownership,
    filter_mass_assignment_payload,
    has_permission,
    validate_ceiling_rule,
    validate_sole_admin_protection,
)

__all__ = [
    # Hasher
    "get_password_hasher",
    "hash_password",
    "verify_password",
    "needs_rehash",
    # Context
    "TenantContext",
    "SecurityContext",
    "set_tenant_context",
    "get_security_context",
    "get_tenant_context",
    # Password policy
    "PasswordPolicyException",
    "validate_password_complexity",
    # Rate Limit
    "check_rate_limit",
    "rate_limit",
    # File Security
    "FileSecurityException",
    "MalwareScanResult",
    "BaseMalwareScanner",
    "NullMalwareScanner",
    "get_malware_scanner",
    "set_malware_scanner",
    "validate_document_upload",
    # Headers
    "SecurityHeadersMiddleware",
    "DEFAULT_CSP_POLICY",
    # AI Security
    "AISecurityException",
    "AIRecommendationEnvelope",
    "sanitize_untrusted_text",
    "detect_prompt_injection_indicators",
    "build_safe_llm_prompt",
    "wrap_advisory_recommendation",
    # Audit
    "SecurityAuditEvent",
    "log_security_event",
    "sanitize_audit_details",
    "sanitize_audit_value",
    # RBAC
    "ROLE_CANDIDATE",
    "ROLE_RECRUITER",
    "ROLE_HIRING_MANAGER",
    "ROLE_ORG_ADMIN",
    "ROLE_PLATFORM_SUPER_ADMIN",
    "has_permission",
    "validate_ceiling_rule",
    "validate_sole_admin_protection",
    "assert_tenant_ownership",
    "assert_user_ownership",
    "filter_mass_assignment_payload",
    # Encryption
    "derive_field_encryption_key",
    "encrypt_sensitive_data",
    "decrypt_sensitive_data",
]
