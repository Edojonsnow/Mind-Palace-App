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

## Rate Limiting

Redis atomically admits expensive work per authenticated user across API and
worker instances. Each bucket has a fixed window starting at its first admitted
request; rejected requests do not extend it. Defaults are configurable:

| Work | Default | Environment variable |
| --- | --- | --- |
| Ask | 10/minute | `RATE_LIMIT_ASK_PER_MINUTE` |
| Query embeddings | 60/minute | `RATE_LIMIT_SEARCH_PER_MINUTE` |
| Organization retries | 10/minute | `RATE_LIMIT_ORGANIZE_PER_MINUTE` |
| Export requests | 3/hour | `RATE_LIMIT_EXPORTS_PER_HOUR` |
| Worker AI jobs | 20/minute | `RATE_LIMIT_AI_JOBS_PER_MINUTE` |

`RATE_LIMITS_ENABLED=false` disables admission checks. Bucket keys contain only
the work type and user ID, never queries, thought bodies, or IP addresses.

Ask, export, and organization admission is checked before side effects. A
denial returns 429 with `Retry-After`; Redis admission outages return 503 with
`Retry-After: 30`. These safe, pre-work rejections release the idempotency claim,
so an explicit retry with the same key can proceed later. Completed idempotent
replays do not consume another allowance. Failed downstream work still consumes
an admission; the limiter is not a billing ledger.

Recall falls back to lexical search rather than making another embedding call
when its allowance is exhausted or Redis is unavailable. It returns 200 with
`X-Search-Fallback` and `Retry-After`; the web displays a text-search notice.
Browsing without a query does not consume the semantic-search allowance.

Thought capture, editing, and AI opt-out remain available independently of AI
allowances. Workers defer limited jobs through RQ's scheduler, storing
`background_jobs.not_before` and keeping the thought pending. Deferred jobs
recheck ownership, deletion, content version, and AI permission before a model
call. A queue dispatch failure marks processing failed without losing the
thought. The existing Postgres-to-Redis dispatch crash gap still requires
operational recovery; this is not a transactional outbox.

These are per-user work limits, not token budgets, daily spending quotas,
global capacity controls, or login/signup abuse protection. Those protections
must be configured separately before a public rollout.

## Verification

Backend tests cover replay, payload conflicts, user isolation, resource
deletion, citation permissions, history-off behavior, exports, worker enqueue
deduplication, expiration, admission rejection, and concurrent claims. Admission
tests cover Retry-After, Redis outages, lexical fallback, job deferral/resumption,
and AI opt-out. Browser fixtures cover retries and user-facing fallback feedback.
