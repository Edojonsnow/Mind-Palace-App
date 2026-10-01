# Request Safety

## Idempotency

`POST /thoughts`, `POST /ask`, `POST /exports`, and
`POST /thoughts/{id}/organize` accept `Idempotency-Key` (1-128 ASCII letters,
digits, hyphens, or underscores). It is optional for older API clients; the web
client supplies a UUID for every action. The same action's retries reuse it;
an intentional new action gets a new key, even if its text is identical.

Claims are uniquely scoped by authenticated user, endpoint, and key in
Postgres. A normalized request hash prevents reusing a key with different
data (409). Concurrent or uncertain attempts return 409 without repeating
work. Completed replay returns the current owned resource and sets
`Idempotency-Replayed: true`, preserving the route's success status.

Operation completion is committed alongside the thought, export, or assistant
message. Records contain references and fingerprints, not copies of private
content. Deleted thought results return 410; Ask replay filters citations
against current AI permissions and deletion state. History-off answers are
not persisted: their replay returns 409 instead of generating another answer.
Account-data purge removes all the user's operation records.

Completed claims are retained for 24 hours by default, configurable with
`IDEMPOTENCY_RETENTION_HOURS`; expired completed records are removed on the
user's next keyed action. A key used after that window can start a new action.
In-progress and uncertain claims do not expire automatically, because a
provider may already have charged or a job may already exist. They require
inspection rather than blind retries. This is not an exactly-once guarantee
across Postgres, Redis, and OpenAI: a crash between committing a job and queue
dispatch may still require operational recovery of the existing job.

The web keeps failed-action keys in user-scoped page memory and clears them
after success/sign-out/account changes. A failed Ask preserves its question
and removes the optimistic message before retry. Reloading the page loses
these keys; browser storage is not used to retain private drafts. API clients
requiring retry across restarts must retain their own keys securely.

AI workers ignore already-completed, cancelled, or running jobs. This prevents
concurrent redelivery from repeating the provider call; a crashed running job
must be inspected/retried through the organization action rather than silently
executed again.

## Verification

Backend tests cover replay, payload conflicts, user isolation, resource
deletion, citation permissions, history-off behavior, exports, worker enqueue
deduplication, expiration, admission rejection, and concurrent claims.
