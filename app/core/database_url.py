def normalize_database_url(database_url: str) -> str:
    """Prefer Psycopg 3 when a plain Neon Postgres URL is supplied."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)

    if database_url.startswith("postgres://"):
        return database_url.replace("postgres://", "postgresql+psycopg://", 1)

    return database_url

