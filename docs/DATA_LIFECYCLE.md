# Data Lifecycle

## Thought Recovery

`DELETE /thoughts/{thought_id}` performs a soft delete. The thought receives a
`deleted_at` timestamp and a `purge_at` timestamp based on
`RECOVERY_WINDOW_DAYS`, which defaults to 30 days.

During the recovery window:

- normal Recall and Ask queries exclude the thought;
- `GET /thoughts/deleted` lists the user's recoverable deleted thoughts;
- `POST /thoughts/{thought_id}/restore` makes the thought active again; and
- its chunks, embeddings, and metadata remain available for restoration.

The API schedules a delayed RQ job when a thought is deleted. The worker runs
with `with_scheduler=True`, so the delayed job survives worker restarts. When
the window expires, the job removes the thought, chunks, embeddings, metadata,
pending thought jobs, and citations to the thought from stored chat messages.

## Exports

`POST /exports` creates a pending export request and a background job. The job
stores a JSON snapshot containing user settings, thoughts, AI metadata, chat
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
When the delayed job runs, it removes thoughts, AI artifacts, chats, exports,
settings, and the local Mind Palace user record.

The current API does not call a Neon Auth administrative endpoint. Therefore,
the Neon Auth identity is outside this data purge and must be removed through a
separate provider integration before production account deletion is described
as fully complete.

## Privacy Checks

Lifecycle jobs log only error types and status information. They must not log
thought bodies, chat messages, export payloads, embeddings, access tokens, or
provider credentials.
