# Data Exposure Audit

## Positive Findings

- Product responses use explicit Pydantic response models rather than returning arbitrary ORM dictionaries.
- Thought, metadata, chunk, book, conversation, message, export, and lifecycle queries are scoped to the authenticated user in the reviewed services.
- Export responses intentionally contain the user's own thought and chat data and are protected by user ownership and expiry checks.
- Logs reviewed use event types, counts, lengths, identifiers for background jobs, and exception class names; they do not log thought bodies, chat messages, prompts, AI responses, access tokens, or database URLs.

## Data-Minimization Recommendations

| Area | Reference | Recommendation |
|---|---|---|
| Thought response | `app/schemas/thought.py:65-91` | Confirm clients need `user_id`, `deleted_at`, and `purge_at`; omit them from normal active-thought responses if not required. |
| Version response | `app/api/routes/health.py:30-36` | Avoid exposing the deployment environment on a public endpoint. |
| User settings update | `app/schemas/settings.py:7-10` | Add `extra="forbid"` for consistency with profile schemas. |
| Auth diagnostics | `app/core/auth.py:62-67` | Current logs avoid tokens; consider whether issuer host details need to be retained in production logs. |

## No Cross-User Exposure Found

The static review found user ownership predicates in the primary object access paths. A dynamic test with two authenticated users is still recommended before production deployment to validate the behavior at the HTTP boundary, especially for UUID-based thought, conversation, export, book, restore, and download routes.
