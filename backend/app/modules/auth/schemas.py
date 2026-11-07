"""Pydantic schemas for identity, authentication, session lifecycle, and MFA."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    """User self-registration request."""

    email: EmailStr = Field(..., description="Canonical user email address")
    password: str = Field(..., min_length=12, max_length=128, description="Strong password")
    first_name: str = Field(..., min_length=1, max_length=100, description="User legal first name")
    last_name: str = Field(..., min_length=1, max_length=100, description="User legal last name")
    phone_number: str | None = Field(default=None, max_length=30, description="Contact phone")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()

    @field_validator("first_name", "last_name")
    @classmethod
    def strip_names(cls, v: str) -> str:
        s = v.strip()
        if not s:
            raise ValueError("Name cannot be empty or whitespace only")
        return s


class LoginRequest(BaseModel):
    """User authentication credentials adhering to Architecture Document 10."""

    email: EmailStr = Field(..., description="User email address")
    password: str = Field(..., description="User plaintext password")
    organization_slug: str | None = Field(
        default=None, description="Optional organization slug for immediate tenant scoping"
    )

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class UserResponse(BaseModel):
    """User response model adhering to Architecture Document 10 Contract 1."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="User unique identifier")
    email: str = Field(..., description="User email address")
    first_name: str = Field(..., description="First name")
    last_name: str = Field(..., description="Last name")
    active_tenant_id: UUID | None = Field(
        default=None, description="Current active tenant identifier"
    )
    role: str | None = Field(default=None, description="Current active role name")
    permissions: list[str] = Field(default_factory=list, description="Resolved capability codes")
    mfa_enabled: bool = Field(default=False, description="MFA protection status")
    is_active: bool = Field(default=True, description="Account active status")


class LoginResponse(BaseModel):
    """Successful authentication response payload."""

    user: UserResponse
    expires_in: int = Field(default=900, description="Access token lifetime in seconds")
    mfa_required: bool = Field(default=False, description="MFA challenge indicator")
    mfa_token: str | None = Field(default=None, description="Temporary MFA challenge token")


class RefreshResponse(BaseModel):
    """Refreshed token response payload."""

    user: UserResponse
    expires_in: int = Field(default=900, description="Access token lifetime in seconds")


class SwitchOrganizationRequest(BaseModel):
    """Tenant context switch request adhering to Architecture Document 07 Section 7."""

    target_tenant_id: UUID = Field(..., description="Target organization UUID")


class MfaEnrollResponse(BaseModel):
    """MFA enrollment payload containing TOTP secret, URI, and one-time backup codes."""

    secret: str = Field(..., description="Plaintext base32 TOTP secret for manual setup")
    otpauth_uri: str = Field(..., description="otpauth:// URI for QR code generation")
    backup_codes: list[str] = Field(..., description="One-time recovery backup codes")


class MfaVerifyRequest(BaseModel):
    """MFA verification code submission."""

    code: str = Field(
        ..., min_length=6, max_length=16, description="6-digit TOTP code or backup code"
    )
    mfa_token: str | None = Field(
        default=None, description="Required when verifying an active login challenge"
    )


class MfaDisableRequest(BaseModel):
    """MFA disable request requiring current credentials."""

    password: str = Field(..., description="Account password for confirmation")
    code: str = Field(..., min_length=6, max_length=16, description="Valid TOTP or backup code")


class PasswordChangeRequest(BaseModel):
    """Authenticated user password modification."""

    current_password: str = Field(..., description="Existing plaintext password")
    new_password: str = Field(..., min_length=12, max_length=128, description="New strong password")


class PasswordResetRequest(BaseModel):
    """Public password reset initiation."""

    email: EmailStr = Field(..., description="Registered account email")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.strip().lower()


class PasswordResetConfirmRequest(BaseModel):
    """Password reset completion with token."""

    token: str = Field(..., description="Cryptographically secure reset token")
    new_password: str = Field(..., min_length=12, max_length=128, description="New strong password")


class SessionSummary(BaseModel):
    """Summary of active user sessions."""

    id: UUID = Field(..., description="Session identifier")
    tenant_id: UUID | None = Field(default=None, description="Associated tenant")
    ip_address: str | None = Field(default=None, description="Client IP address")
    user_agent: str | None = Field(default=None, description="Client user agent")
    created_at: datetime = Field(..., description="Session creation timestamp")
    expires_at: datetime = Field(..., description="Session expiration timestamp")
    is_current: bool = Field(default=False, description="Whether this is the caller's session")
