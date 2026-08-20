from functools import lru_cache
from pathlib import Path

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
    ask_top_k: int = 5
    ask_history_messages: int = 10
    ask_max_context_chars: int = 12000

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
