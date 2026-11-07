"""Application settings and environment configuration management using Pydantic v2."""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

INSECURE_PASSWORDS: frozenset[str] = frozenset(
    {
        "local_development_password_only",
        "postgres",
        "password",
        "admin",
        "root",
        "123456",
        "",
    }
)


class Settings(BaseSettings):
    """Canonical application settings conforming to the Step 2 architecture."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 1. General & Environment
    ENVIRONMENT: str = Field(
        default="development",
        description="Environment mode: development, testing, staging, production",
    )
    APP_NAME: str = Field(
        default="AI HR Intelligence Platform", description="Application display name"
    )
    APP_VERSION: str = Field(default="2.0.0", description="Semver application version")
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Standard logging level")

    # 2. Server & Networking
    BACKEND_HOST: str = Field(default="0.0.0.0", description="Host address to bind")
    BACKEND_PORT: int = Field(default=8000, description="Port to listen on")
    BACKEND_CORS_ORIGINS: list[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origin domains",
    )

    # 3. Database (PostgreSQL 16 + pgvector)
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="ai_hr_db", description="Database name")
    POSTGRES_USER: str = Field(default="aihr_app_user", description="Database application user")
    POSTGRES_PASSWORD: str = Field(
        default="local_development_password_only", description="Database password"
    )

    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://aihr_app_user:local_development_password_only@localhost:5432/ai_hr_db",
        description="Asynchronous database connection URI",
    )
    DATABASE_SYNC_URL: str = Field(
        default="postgresql://aihr_app_user:local_development_password_only@localhost:5432/ai_hr_db",
        description="Synchronous database connection URI for Alembic migrations",
    )

    DB_POOL_SIZE: int = Field(default=20, description="Connection pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="Max overflow connections")
    DB_POOL_TIMEOUT: int = Field(default=30, description="Pool connection timeout seconds")
    DB_POOL_RECYCLE: int = Field(default=1800, description="Recycle connections every 30 minutes")

    # 4. Redis 7 Cache & Task Broker
    REDIS_HOST: str = Field(default="localhost", description="Redis host")
    REDIS_PORT: int = Field(default=6379, description="Redis port")
    REDIS_PASSWORD: str = Field(default="", description="Redis password")
    REDIS_DB: int = Field(default=0, description="Redis database index")
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URI")

    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1", description="Celery broker URI"
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/2", description="Celery result backend URI"
    )

    # 5. Security & Authentication
    JWT_SECRET_KEY: str = Field(
        default="local_development_jwt_secret_key_minimum_32_characters_long_for_security",
        description="HMAC secret key for signing JWT tokens",
    )
    MFA_ENCRYPTION_KEY: str = Field(
        default="local_development_mfa_encryption_key_minimum_32_characters_for_security",
        description="Dedicated cryptographic key for AES-256-GCM encryption of MFA secrets at rest",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, description="Short-lived access token TTL")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Sliding refresh token TTL")

    COOKIE_SECURE: bool = Field(
        default=False, description="Set True in staging/production for HTTPS cookies"
    )
    COOKIE_SAMESITE: str = Field(default="lax", description="SameSite cookie policy")
    COOKIE_DOMAIN: str = Field(default="localhost", description="Cookie domain boundary")

    # Tracking & Correlation Headers
    CORRELATION_ID_HEADER: str = Field(
        default="X-Correlation-ID", description="Correlation tracking header"
    )
    REQUEST_ID_HEADER: str = Field(
        default="X-Request-ID", description="Alternative request ID header"
    )

    # Argon2id Hashing Configuration (OWASP / AC-SEC-03 compliant: memory_cost >= 64MB)
    ARGON2_TIME_COST: int = Field(default=3, description="Argon2id iteration count")
    ARGON2_MEMORY_COST: int = Field(
        default=65536, description="Argon2id memory cost in KiB (64 MB)"
    )
    ARGON2_PARALLELISM: int = Field(default=4, description="Argon2id parallelism lanes")
    ARGON2_HASH_LEN: int = Field(default=32, description="Argon2id hash length")
    ARGON2_SALT_LEN: int = Field(default=16, description="Argon2id salt length")

    # 6. Storage (AWS S3)
    AWS_REGION: str = Field(default="us-east-1", description="AWS Region")
    AWS_ACCESS_KEY_ID: str = Field(default="", description="AWS Access Key")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", description="AWS Secret Key")
    S3_BUCKET_RESUMES: str = Field(default="ai-hr-resumes-local", description="Resume S3 Bucket")
    S3_BUCKET_REPORTS: str = Field(default="ai-hr-reports-local", description="Report S3 Bucket")
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = Field(
        default=900, description="Presigned URL expiration in seconds"
    )

    # 7. AI & Embeddings
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    EMBEDDING_MODEL_NAME: str = Field(
        default="text-embedding-3-small", description="Default vector model"
    )
    EMBEDDING_DIMENSION: int = Field(default=1536, description="Vector dimension size")
    LLM_MODEL_NAME: str = Field(default="gpt-4o-mini", description="Default LLM model")

    @model_validator(mode="after")
    def validate_security_settings(self) -> "Settings":
        """Enforce strict production secret safeguards and prevent insecure defaults."""
        if self.ENVIRONMENT in ("production", "staging"):
            # 1. JWT Secret Key Validation
            if "local_development" in self.JWT_SECRET_KEY or len(self.JWT_SECRET_KEY) < 32:
                raise ValueError(
                    "Insecure or default JWT_SECRET_KEY detected for production/staging (minimum 32 chars required)"
                )

            # 2. MFA Encryption Key Validation (Key separation guarantee)
            if "local_development" in self.MFA_ENCRYPTION_KEY or len(self.MFA_ENCRYPTION_KEY) < 32:
                raise ValueError(
                    "Insecure or default MFA_ENCRYPTION_KEY detected for production/staging (minimum 32 chars required)"
                )
            if self.MFA_ENCRYPTION_KEY == self.JWT_SECRET_KEY:
                raise ValueError(
                    "Security violation: MFA_ENCRYPTION_KEY must be separate and distinct from JWT_SECRET_KEY"
                )

            # 3. POSTGRES_PASSWORD Validation
            if (
                "local_development" in self.POSTGRES_PASSWORD
                or self.POSTGRES_PASSWORD in INSECURE_PASSWORDS
            ):
                raise ValueError(
                    "Insecure default POSTGRES_PASSWORD detected for production/staging"
                )

            # 3. DATABASE_URL Validation (Asynchronous URI)
            try:
                db_url = make_url(self.DATABASE_URL)
            except Exception as exc:
                raise ValueError(f"Invalid DATABASE_URL configuration: {exc}") from exc

            db_password = db_url.password or ""
            if (
                not db_password
                or db_password in INSECURE_PASSWORDS
                or "local_development" in db_password
            ):
                raise ValueError(
                    "Insecure default or development password detected in DATABASE_URL for production/staging"
                )
            if db_password != self.POSTGRES_PASSWORD:
                raise ValueError(
                    "Database credential mismatch: DATABASE_URL password does not match POSTGRES_PASSWORD"
                )
            if self.POSTGRES_USER and db_url.username != self.POSTGRES_USER:
                raise ValueError(
                    "Database credential mismatch: DATABASE_URL username does not match POSTGRES_USER"
                )

            # 4. DATABASE_SYNC_URL Validation (Synchronous URI for Alembic)
            try:
                sync_url = make_url(self.DATABASE_SYNC_URL)
            except Exception as exc:
                raise ValueError(f"Invalid DATABASE_SYNC_URL configuration: {exc}") from exc

            sync_password = sync_url.password or ""
            if (
                not sync_password
                or sync_password in INSECURE_PASSWORDS
                or "local_development" in sync_password
            ):
                raise ValueError(
                    "Insecure default or development password detected in DATABASE_SYNC_URL for production/staging"
                )
            if sync_password != self.POSTGRES_PASSWORD:
                raise ValueError(
                    "Database credential mismatch: DATABASE_SYNC_URL password does not match POSTGRES_PASSWORD"
                )
            if sync_password != db_password:
                raise ValueError(
                    "Database credential mismatch: DATABASE_URL and DATABASE_SYNC_URL passwords do not match"
                )
            if self.POSTGRES_USER and sync_url.username != self.POSTGRES_USER:
                raise ValueError(
                    "Database credential mismatch: DATABASE_SYNC_URL username does not match POSTGRES_USER"
                )

            # 5. Cookie Security
            if not self.COOKIE_SECURE:
                raise ValueError("COOKIE_SECURE must be True in production/staging environments")
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
