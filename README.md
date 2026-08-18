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

Run the API:

```bash
uvicorn app.main:app --reload
```

Run tests:

```bash
pytest
```

## MVP Defaults

- `use_with_ask_my_mind` defaults to `false`.
- Thought bodies are server-readable in the MVP.
- Raw thought bodies, chat messages, prompts, and AI responses must not be logged.
- Local-only thought storage is deferred until the mobile app phase.

