from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.database_url import normalize_database_url

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Mind Palace App"
    app_env: str = "local"
    app_version: str = "0.1.0"
    database_url: str = "postgresql+psycopg://user:password@localhost:5432/mind_palace"
    neon_auth_jwks_url: str | None = None
    neon_auth_issuer: str | None = None
    neon_auth_audience: str | None = None
    neon_auth_base_url: str | None = None
    health_db_check_token: SecretStr | None = None
    backend_cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    openai_api_key: str | None = None
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1536
    openai_metadata_model: str = "gpt-4.1-mini"
    openai_answer_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 30.0
    redis_url: str = "redis://localhost:6379/0"
    ai_queue_name: str = "mind-palace-ai"
    ai_chunk_size_chars: int = 1600
    ai_chunk_overlap_chars: int = 200
    ai_reconciliation_interval_seconds: int = Field(default=30, ge=5)
    ai_reconciliation_batch_size: int = Field(default=50, ge=1, le=500)
    ai_job_stale_after_seconds: int = Field(default=900, ge=60)
    ai_queue_retry_delay_seconds: int = Field(default=60, ge=5)
    account_deletion_reconciliation_batch_size: int = Field(default=50, ge=1, le=500)
    account_deletion_retry_max: int = Field(default=5, ge=1)
    account_deletion_retry_interval_seconds: int = Field(default=300, ge=5)
    ask_top_k: int = 5
    ask_history_messages: int = 10
    ask_max_context_chars: int = 12000
    recovery_window_days: int = Field(default=60, ge=1)
    export_retention_hours: int = 24
    idempotency_retention_hours: int = 24
    neon_api_key: str | None = None
    neon_project_id: str | None = None
    neon_auth_branch_id: str | None = None
    neon_management_api_base_url: str = "https://console.neon.tech/api/v2"
    neon_management_api_timeout_seconds: float = Field(default=10.0, ge=1.0)
    rate_limits_enabled: bool = True
    rate_limit_ask_per_minute: int = Field(default=10, ge=1)
    rate_limit_search_per_minute: int = Field(default=60, ge=1)
    rate_limit_organize_per_minute: int = Field(default=10, ge=1)
    rate_limit_exports_per_hour: int = Field(default=3, ge=1)
    rate_limit_ai_jobs_per_minute: int = Field(default=20, ge=1)
    rate_limit_thought_writes_per_minute: int = Field(default=60, ge=1)
    rate_limit_book_writes_per_minute: int = Field(default=20, ge=1)
    rate_limit_profile_writes_per_minute: int = Field(default=20, ge=1)
    rate_limit_settings_writes_per_minute: int = Field(default=20, ge=1)
    rate_limit_account_deletion_per_hour: int = Field(default=5, ge=1)
    auth_rate_limits_enabled: bool = False
    auth_rate_limit_token: SecretStr | None = None
    auth_rate_limit_sign_up_per_window: int = Field(default=5, ge=1)
    auth_rate_limit_sign_in_per_window: int = Field(default=10, ge=1)
    auth_rate_limit_verification_per_window: int = Field(default=5, ge=1)
    auth_rate_limit_password_reset_per_window: int = Field(default=5, ge=1)
    ai_quotas_enabled: bool = True
    ai_daily_quota_units: int = Field(default=200, ge=1)
    ai_quota_ask_units: int = Field(default=2, ge=1)
    ai_quota_search_units: int = Field(default=1, ge=1)
    ai_quota_organization_units: int = Field(default=2, ge=1)
    ai_max_thought_chars: int = Field(default=50000, ge=1000)

    @field_validator("neon_auth_audience", mode="before")
    @classmethod
    def normalize_auth_audience(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def require_production_security_configuration(self) -> "Settings":
        if self.app_env.strip().lower() in {"staging", "production"}:
            missing: list[str] = []
            if not self.neon_auth_audience:
                missing.append("NEON_AUTH_AUDIENCE")
            if (
                self.health_db_check_token is None
                or not self.health_db_check_token.get_secret_value().strip()
            ):
                missing.append("HEALTH_DB_CHECK_TOKEN")
            if not self.auth_rate_limits_enabled:
                missing.append("AUTH_RATE_LIMITS_ENABLED=true")
            if (
                self.auth_rate_limit_token is None
                or not self.auth_rate_limit_token.get_secret_value().strip()
            ):
                missing.append("AUTH_RATE_LIMIT_TOKEN")
            if not missing:
                return self
            raise ValueError(
                "Production security configuration is missing: " + ", ".join(missing)
            )
        return self

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        return normalize_database_url(self.database_url)

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.backend_cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
