# Profile And AI Personalization

## API

All endpoints use the authenticated app user; no user ID is accepted in the payload.

- `GET /profile`: preferred name (`display_name`), email, and avatar URL.
- `PATCH /profile`: update or clear preferred name and avatar URL. Email is read-only.
- `GET /profile/ai-preferences`: return saved preferences or opt-out defaults.
- `PATCH /profile/ai-preferences`: update only supplied preference fields.

Account fields belong to `users`; AI preferences live in the separate
`ai_preferences` table, with one row per user. Avatar URLs must use HTTPS.
This release accepts an image URL, not a file upload; the API never downloads
the image. Password recovery stays with Neon Auth's existing email-code flow.

Writing style supports `natural`, `conversational`, and `formal`. Response
detail supports `concise`, `balanced`, and `detailed`. Goals and interests
each accept up to 20 nonempty entries, with 200 characters per entry.

## Consent And Ask

`use_profile_context` defaults to false, independently of thought AI permissions.
Saving preferences does not enable it. The web consent toggle saves immediately,
without submitting unsaved preference drafts.

When enabled, the answer-generation request may contain preferred name, writing
style, response detail, goals, and interests. Email and avatar are excluded.
Profile values are treated as untrusted preference data, not instructions or
memory evidence. They do not become embeddings, change retrieval, or become
citations. No AI-enabled thought sources still means no provider request.

The backend checks consent for each answer-generation request. Disabling it
keeps preferences saved but omits them from future requests. A request already
sent to the provider cannot be recalled. Saved chats may still contain answers
influenced by earlier preferences; opt-out does not rewrite or delete history.

This is server-readable cloud storage, not end-to-end encryption. The profile
is private, user-scoped, and has no public or social surface.

## Lifecycle And Setup

Exports include profile fields and AI preferences even when AI context is off.
The export format is version 2. Account-data purge deletes preferences before
the user record. Neon Auth identity deletion retains the existing limitation
documented in `DATA_LIFECYCLE.md`.

Apply migration `20261001_0008` before running the updated API or worker:

```bash
.venv/bin/alembic upgrade head
docker compose up --build -d api worker
```

Use the intended environment's database configuration; never apply a
development change to a production database accidentally.
