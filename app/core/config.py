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
    openai_api_key: str | None = None
    redis_url: str = "redis://localhost:6379/0"

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
    )

    @property
    def sqlalchemy_database_url(self) -> str:
        return normalize_database_url(self.database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
