# Data Lifecycle

## Thought Recovery

`DELETE /thoughts/{thought_id}` performs a soft delete. The thought receives a
`deleted_at` timestamp and a `purge_at` timestamp based on
`RECOVERY_WINDOW_DAYS`, which defaults to 60 days.

During the recovery window:

- normal Recall and Ask queries exclude the thought;
- `GET /thoughts/deleted` lists the user's recoverable deleted thoughts;
- `POST /thoughts/{thought_id}/restore` makes the thought active again; and
- its chunks, embeddings, and metadata remain available for restoration.

The API schedules a delayed RQ job when a thought is deleted. The worker runs
with `with_scheduler=True`, so the delayed job survives worker restarts. When
the window expires, the job removes the thought, chunks, embeddings, metadata,
pending thought jobs, and citations to the thought from stored chat messages.
The worker reconciliation loop also purges expired thoughts directly if a
scheduled job was lost.

## Exports

`POST /exports` creates a pending export request and a background job. The job
stores a version-2 JSON snapshot containing profile fields, AI preferences,
user settings, thoughts, AI metadata, chat
conversations, and chat messages. It does not include embeddings or internal
job records.

Clients poll `GET /exports/{export_id}` and download completed data with
`GET /exports/{export_id}/download`. The payload expires after
`EXPORT_RETENTION_HOURS`, which defaults to 24 hours. Expiry removes the
payload while retaining a small status record until a later export request
cleans it up.

## Account Deletion

`POST /account/deletion` schedules deletion of all Mind Palace data after the
same recovery window. `DELETE /account/deletion` cancels a pending request.
When the delayed job runs, it first permanently deletes the user's Neon Auth
identity through the branch-scoped Neon management API, then removes thoughts,
AI artifacts, chats, exports, settings, AI preferences, profile fields, and the
local Mind Palace user record. The worker treats an already-missing Neon Auth
identity as success so an interrupted purge can be retried safely.

Production account deletion requires `NEON_API_KEY`, `NEON_PROJECT_ID`, and
`NEON_AUTH_BRANCH_ID`. The API fails closed when those values are missing; it
does not purge local data while the Auth identity cannot be deleted.
The account purge job retries transient failures through RQ and the worker
reconciliation loop requeues due requests whose scheduled job was lost.

## Privacy Checks

Lifecycle jobs log only error types and status information. They must not log
thought bodies, chat messages, export payloads, embeddings, access tokens, or
provider credentials.
