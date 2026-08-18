# Mind Palace App

Backend/API service for Mind Palace.

## Stack

- Python 3.12+
- FastAPI
- SQLAlchemy
- Alembic
- Neon Postgres
- RQ/Redis later for background jobs

## Local Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

For normal local work against Neon development:

```bash
cp .env.development.example .env
```

Paste your Neon development branch connection string into `DATABASE_URL`.

Neon usually provides a URL like:

```bash
DATABASE_URL="postgresql://user:password@ep-example.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
```

The app normalizes `postgresql://` to SQLAlchemy's Psycopg 3 driver URL internally, so you can paste the Neon URL directly.

See [Database Environments](docs/DATABASE_ENVIRONMENTS.md) for development, staging, and production setup.

Run the API:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

Check the database connection:

```bash
python scripts/check_neon_connection.py
```

Check DB health while the API is running:

```bash
curl http://127.0.0.1:8000/health/db
```

## MVP Defaults

- `use_with_ask_my_mind` defaults to `false`.
- Thought bodies are server-readable in the MVP.
- Raw thought bodies, chat messages, prompts, and AI responses must not be logged.
- Local-only thought storage is deferred until the mobile app phase.
