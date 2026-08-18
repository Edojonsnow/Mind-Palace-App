from app.core.config import PROJECT_ROOT
from app.core.database_url import normalize_database_url


def test_normalize_neon_postgresql_url_to_psycopg_driver() -> None:
    url = "postgresql://user:password@example.neon.tech/neondb?sslmode=require"

    assert (
        normalize_database_url(url)
        == "postgresql+psycopg://user:password@example.neon.tech/neondb?sslmode=require"
    )


def test_normalize_legacy_postgres_url_to_psycopg_driver() -> None:
    url = "postgres://user:password@example.neon.tech/neondb?sslmode=require"

    assert (
        normalize_database_url(url)
        == "postgresql+psycopg://user:password@example.neon.tech/neondb?sslmode=require"
    )


def test_leave_explicit_sqlalchemy_driver_url_unchanged() -> None:
    url = "postgresql+psycopg://user:password@example.neon.tech/neondb?sslmode=require"

    assert normalize_database_url(url) == url


def test_project_root_points_to_backend_repo() -> None:
    assert (PROJECT_ROOT / "pyproject.toml").exists()
    assert (PROJECT_ROOT / "app").is_dir()
