# Mind Palace App

Backend/API service for Mind Palace.

## Stack

- Python 3.12+
- FastAPI
- SQLAlchemy
- Alembic
- Neon Postgres
- RQ/Redis for background jobs

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

The Docker setup runs the API, an RQ worker, and Redis. Neon remains the
database, so no local Postgres container is required. The worker processes only
thoughts whose `use_with_ask_my_mind` value is `true`.

Make sure `.env` contains the Neon development database and auth settings,
then start the API with:

```bash
docker compose up --build
```

The API and worker use `redis://redis:6379/0` inside Compose. When running the
API directly on the host, use the local default `redis://localhost:6379/0` and
start Redis separately.

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

## AI Processing

AI participation is opt-in per thought. Saving a thought with AI disabled only
writes the original thought and deterministic fields. It does not enqueue a
job, call OpenAI, create chunks, or create embeddings.

When AI is enabled, the API saves the thought first and creates a pending
`background_jobs` row. RQ sends the job to the worker, which:

1. splits the thought into overlapping text chunks;
2. creates an embedding for each chunk with OpenAI's embedding endpoint;
3. extracts structured metadata with an OpenAI model; and
4. stores the derived artifacts and marks the thought ready for retrieval.

The original thought remains the source record. Chunks, embeddings, and AI
metadata are derived artifacts that can be rebuilt or purged. Turning AI off
deletes those artifacts and cancels pending or running jobs. OpenAI failures
mark the job and thought as failed without undoing the saved thought.

The current implementation uses `text-embedding-3-small` with 1536 dimensions
and a configurable metadata model. The embedding dimension is part of the
database schema; changing it requires a migration.

## Ask My Mind

The retrieval MVP is available at `POST /ask`. It embeds the question, searches
the authenticated user's ready thought chunks with pgvector, asks OpenAI for a
structured answer grounded in those sources, and returns citation data for the
client source panel. Chat history is stored by default and can be disabled with
the `store_chat_history` user setting.

The current endpoint answers from saved thoughts only. Web search, streaming,
and mobile offline chat are separate follow-up implementations. See
`docs/ASK_MY_MIND.md` for the request flow and technical design.
