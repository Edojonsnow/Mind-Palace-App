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
NEON_AUTH_BASE_URL=
```

For Neon Auth, `NEON_AUTH_ISSUER` is the Auth host origin. Do not append the
`/neondb/auth` path. The JWKS URL does include that path:

```bash
NEON_AUTH_ISSUER=https://<auth-host>
NEON_AUTH_JWKS_URL=https://<auth-host>/neondb/auth/.well-known/jwks.json
```

`NEON_AUTH_AUDIENCE` may remain blank for local/development environments when
audience validation is intentionally disabled. It is required in staging and
production and must exactly match the `aud` claim issued by Neon Auth. The API
will refuse to start in those environments when it is missing.

`NEON_AUTH_BASE_URL` is the Neon Auth API base URL (`https://<auth-host>/neondb/auth`). It is used to validate opaque session tokens when a JWT is not available. If omitted, the API derives it from `NEON_AUTH_JWKS_URL`.

`/health` is the public liveness endpoint. In staging and production,
`/health/db` requires the `X-Health-Check-Token` header matching
`HEALTH_DB_CHECK_TOKEN`; keep this endpoint restricted to trusted monitoring or
private networking. Render should use `/health` for ordinary liveness checks.

For staging and production, enable the shared Redis limiter used by the web
authentication proxy with the same private token configured in Vercel:

```bash
AUTH_RATE_LIMITS_ENABLED=true
AUTH_RATE_LIMIT_TOKEN=<random-shared-secret>
```

The internal `/internal/auth-rate-limit` route is not included in OpenAPI and
requires that token. It admits sign-up, sign-in, verification, and password
reset requests before Neon Auth receives them. Keep the token out of browser
environment variables and leave the feature disabled in local development
unless the web proxy is also configured to call the local API.
In staging and production, the API refuses to start unless this protection is
enabled and the token is configured. Restrict the route at the deployment edge
or through private networking where the platform supports it; the shared token
remains required even when network restrictions are present.

Permanent account deletion also requires a server-side Neon API key and the
target project and branch identifiers:

```bash
NEON_API_KEY=
NEON_PROJECT_ID=
NEON_AUTH_BRANCH_ID=
NEON_MANAGEMENT_API_BASE_URL=https://console.neon.tech/api/v2
```

Keep `NEON_API_KEY` in the real environment only; never commit it or expose it
to the web client. The account deletion worker uses these values to delete the
Neon Auth identity after the 60-day recovery window.

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

The RQ worker also runs a database-backed AI job reconciler every 30 seconds by
default. It repairs AI jobs that were committed before Redis dispatch, reclaims
stale worker jobs, and retries temporary queue failures. Configure the interval,
batch size, stale threshold, and queue retry delay with
`AI_RECONCILIATION_INTERVAL_SECONDS`, `AI_RECONCILIATION_BATCH_SIZE`,
`AI_JOB_STALE_AFTER_SECONDS`, and `AI_QUEUE_RETRY_DELAY_SECONDS`.

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

Temporary Redis dispatch failures keep the job pending with retry backoff. The
worker reconciler repairs pending jobs whose dispatch was lost and reclaims
stale jobs after a worker interruption.

AI work also has a durable per-user daily quota. Ask My Mind and organization
reserve weighted units before provider calls, while explicitly requested
semantic search falls back to lexical search when its allowance is exhausted.
View the current counters with `GET /settings/ai-usage`; configure the default
allowance and action weights with the `AI_DAILY_QUOTA_UNITS` and `AI_QUOTA_*`
environment variables.

The current implementation uses `text-embedding-3-small` with 1536 dimensions
and a configurable metadata model. The embedding dimension is part of the
database schema; changing it requires a migration.

## Recall

`GET /thoughts` is the Recall endpoint. It returns the authenticated user's
non-deleted thoughts as a list, preserving the response shape used by the web
client. Results can be narrowed with these query parameters:

- `q`: case-insensitive keyword search across title, body, source, and book fields;
- `thought_type`: `thought`, `journal`, `quote`, or `book_excerpt`;
- `source_type`: `manual`, `book`, `article`, `website`, `audio`, `import`, or `unknown`;
- `tag`: an exact manual tag;
- `book`: case-insensitive search across book title and author;
- `is_archived`: explicitly include only archived or non-archived thoughts;
- `created_from` and `created_to`: inclusive ISO 8601 timestamp bounds;
- `page`: one-based page number, defaulting to `1`; and
- `page_size`: result count per page from `1` to `100`, defaulting to `20`.

Pagination metadata is returned in `X-Total-Count`, `X-Page`, `X-Page-Size`,
and `X-Total-Pages` response headers. Without filters, the endpoint keeps the
previous behavior and returns all visible thoughts ordered newest first.

The MVP uses database-backed case-insensitive substring matching. PostgreSQL
full-text search or a dedicated search index can be added later if Recall
volume makes substring search too slow.

## Ask My Mind

The retrieval MVP is available at `POST /ask`. It embeds the question, searches
the authenticated user's ready thought chunks with pgvector, asks OpenAI for a
structured answer grounded in those sources, and returns citation data for the
client source panel. Chat history is stored by default and can be disabled with
the `store_chat_history` user setting.

The current endpoint answers from saved thoughts only. Web search, streaming,
and mobile offline chat are separate follow-up implementations. See
`docs/ASK_MY_MIND.md` for the request flow and technical design.

See [Data Lifecycle](docs/DATA_LIFECYCLE.md) for recovery, export, and account
deletion behavior.
