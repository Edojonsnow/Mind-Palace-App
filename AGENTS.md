# AGENTS.md

Guidance for coding agents working in this repository.

## Project

Mind Palace App is the backend API for Mind Palace. It is a separate repository from the planned web and mobile clients.

Core stack:

- Python 3.12+
- FastAPI
- SQLAlchemy
- Alembic
- Neon Postgres
- Neon Auth
- RQ/Redis later for background jobs

## Local Commands

Use the repository virtual environment, especially if a global Anaconda Python is active:

```bash
.venv/bin/python scripts/check_neon_connection.py
.venv/bin/ruff check .
.venv/bin/pytest
python3 -m compileall app migrations scripts tests
```

Run migrations only when intentionally applying schema changes to the active `DATABASE_URL`:

```bash
.venv/bin/alembic upgrade head
```

## Environment

- Real secrets belong in `.env`.
- Commit only example files such as `.env.example`, `.env.development.example`, `.env.staging.example`, and `.env.production.example`.
- Do not print database URLs, access tokens, API keys, thought bodies, chat messages, prompts, or AI responses in logs or test output.

## Code Layout

- `app/api/routes/`: HTTP route handlers and status codes.
- `app/schemas/`: Pydantic request and response shapes.
- `app/models/`: SQLAlchemy database tables.
- `app/services/`: business rules and database operations.
- `app/core/auth.py`: bearer token verification and authenticated-user boundary.
- `migrations/versions/`: Alembic database migrations.

Keep user-owned reads and writes scoped by the authenticated user.

## Product Rules

- `use_with_ask_my_mind` defaults to `false`.
- AI-disabled thoughts are still cloud-synced, but must not be embedded, summarized, retrieved for Ask, or sent to OpenAI.
- Thought bodies are server-readable in the MVP.
- Local-only device storage is deferred until the mobile app phase; the backend should reject local-device-only thoughts for now.
- Deletes use a recovery window before permanent purge.
- Chat history is stored quietly for continuity.

## Change Rules

- Add an Alembic migration for database model changes.
- Keep changes narrow and aligned with the existing route/schema/service/model split.
- Do not add frontend, mobile, AI, queue, or storage-object behavior before the implementation plan reaches that phase.

## Commit Messages

- Use an imperative subject that clearly names the change.
- Include a short body explaining the main implementation details, user-facing impact, and verification when relevant.
- Avoid one-line-only commit messages for implementation work.
