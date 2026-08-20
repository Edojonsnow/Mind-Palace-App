# CLAUDE.md

Follow `AGENTS.md` in this repository.

Most important reminders:

- Use `.venv/bin/python`, `.venv/bin/pytest`, and `.venv/bin/ruff` for local checks.
- Keep route, schema, service, and model responsibilities separate.
- Scope all user-owned data by the authenticated user.
- Do not log thought bodies, chat messages, prompts, AI responses, database URLs, tokens, or API keys.
- Keep `use_with_ask_my_mind` defaulted off.
- Do not implement local-only storage until the mobile phase.
