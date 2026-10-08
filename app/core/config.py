from functools import lru_cache
from pathlib import Path

from pydantic import Field
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
    ask_top_k: int = 5
    ask_history_messages: int = 10
    ask_max_context_chars: int = 12000
    recovery_window_days: int = 30
    export_retention_hours: int = 24
    idempotency_retention_hours: int = 24
    rate_limits_enabled: bool = True
    rate_limit_ask_per_minute: int = Field(default=10, ge=1)
    rate_limit_search_per_minute: int = Field(default=60, ge=1)
    rate_limit_organize_per_minute: int = Field(default=10, ge=1)
    rate_limit_exports_per_hour: int = Field(default=3, ge=1)
    rate_limit_ai_jobs_per_minute: int = Field(default=20, ge=1)
    ai_quotas_enabled: bool = True
    ai_daily_quota_units: int = Field(default=200, ge=1)
    ai_quota_ask_units: int = Field(default=2, ge=1)
    ai_quota_search_units: int = Field(default=1, ge=1)
    ai_quota_organization_units: int = Field(default=2, ge=1)
    ai_max_thought_chars: int = Field(default=50000, ge=1000)

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
