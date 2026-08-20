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

Protected API routes expect a Neon Auth access token:

```bash
Authorization: Bearer <access-token>
```

Set these auth values in `.env`:

```bash
NEON_AUTH_JWKS_URL=
NEON_AUTH_ISSUER=
NEON_AUTH_AUDIENCE=
```

For Neon Auth, `NEON_AUTH_ISSUER` is the Auth host origin. Do not append the
`/neondb/auth` path. The JWKS URL does include that path:

```bash
NEON_AUTH_ISSUER=https://<auth-host>
NEON_AUTH_JWKS_URL=https://<auth-host>/neondb/auth/.well-known/jwks.json
```

`NEON_AUTH_AUDIENCE` is optional. Keep it blank unless the Neon Auth token is issued with a specific audience claim.

See [Database Environments](docs/DATABASE_ENVIRONMENTS.md) for development, staging, and production setup.

Run the API:

```bash
uvicorn app.main:app --reload
```

## Docker

The MVP Docker setup runs only the API. Neon remains the database, so no local
Postgres container is required. Redis will be added when background jobs are
implemented.

Make sure `.env` contains the Neon development database and auth settings,
then start the API with:

```bash
docker compose up --build
```

Apply database migrations through the same container:

```bash
docker compose run --rm api alembic upgrade head
```

The API is available at `http://127.0.0.1:8000`.

Run tests:

```bash
pytest
```

When Anaconda or another global Python is active, prefer the virtual environment explicitly:

```bash
.venv/bin/python scripts/check_neon_connection.py
.venv/bin/pytest
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
