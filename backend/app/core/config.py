"""Application settings and environment configuration management using Pydantic v2."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Canonical application settings conforming to the Step 2 architecture."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # 1. General & Environment
    ENVIRONMENT: str = Field(default="development", description="Environment mode: development, testing, staging, production")
    APP_NAME: str = Field(default="AI HR Intelligence Platform", description="Application display name")
    APP_VERSION: str = Field(default="2.0.0", description="Semver application version")
    DEBUG: bool = Field(default=False, description="Enable debug mode")
    LOG_LEVEL: str = Field(default="INFO", description="Standard logging level")

    # 2. Server & Networking
    BACKEND_HOST: str = Field(default="0.0.0.0", description="Host address to bind")
    BACKEND_PORT: int = Field(default=8000, description="Port to listen on")
    BACKEND_CORS_ORIGINS: List[str] = Field(
        default=["http://localhost:3000", "http://127.0.0.1:3000"],
        description="Allowed CORS origin domains",
    )

    # 3. Database (PostgreSQL 16 + pgvector)
    POSTGRES_HOST: str = Field(default="localhost", description="PostgreSQL host")
    POSTGRES_PORT: int = Field(default=5432, description="PostgreSQL port")
    POSTGRES_DB: str = Field(default="ai_hr_db", description="Database name")
    POSTGRES_USER: str = Field(default="aihr_app_user", description="Database application user")
    POSTGRES_PASSWORD: str = Field(default="local_development_password_only", description="Database password")

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

    CELERY_BROKER_URL: str = Field(default="redis://localhost:6379/1", description="Celery broker URI")
    CELERY_RESULT_BACKEND: str = Field(default="redis://localhost:6379/2", description="Celery result backend URI")

    # 5. Security & Authentication
    JWT_SECRET_KEY: str = Field(
        default="local_development_jwt_secret_key_minimum_32_characters_long_for_security",
        description="HMAC secret key for signing JWT tokens",
    )
    JWT_ALGORITHM: str = Field(default="HS256", description="JWT algorithm")
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=15, description="Short-lived access token TTL")
    REFRESH_TOKEN_EXPIRE_DAYS: int = Field(default=7, description="Sliding refresh token TTL")

    COOKIE_SECURE: bool = Field(default=False, description="Set True in staging/production for HTTPS cookies")
    COOKIE_SAMESITE: str = Field(default="lax", description="SameSite cookie policy")
    COOKIE_DOMAIN: str = Field(default="localhost", description="Cookie domain boundary")

    # 6. Storage (AWS S3)
    AWS_REGION: str = Field(default="us-east-1", description="AWS Region")
    AWS_ACCESS_KEY_ID: str = Field(default="", description="AWS Access Key")
    AWS_SECRET_ACCESS_KEY: str = Field(default="", description="AWS Secret Key")
    S3_BUCKET_RESUMES: str = Field(default="ai-hr-resumes-local", description="Resume S3 Bucket")
    S3_BUCKET_REPORTS: str = Field(default="ai-hr-reports-local", description="Report S3 Bucket")
    S3_PRESIGNED_URL_EXPIRE_SECONDS: int = Field(default=900, description="Presigned URL expiration in seconds")

    # 7. AI & Embeddings
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key")
    EMBEDDING_MODEL_NAME: str = Field(default="text-embedding-3-small", description="Default vector model")
    EMBEDDING_DIMENSION: int = Field(default=1536, description="Vector dimension size")
    LLM_MODEL_NAME: str = Field(default="gpt-4o-mini", description="Default LLM model")


@lru_cache
def get_settings() -> Settings:
    """Return a cached singleton instance of application settings."""
    return Settings()
