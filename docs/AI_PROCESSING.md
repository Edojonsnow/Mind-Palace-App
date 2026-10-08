# Mind Palace AI Processing

## The Core Design

The original thought is the source record. AI output is derived data.

```text
thoughts
  ├── thought_chunks       searchable text windows
  ├── embeddings           vector representation of each chunk
  └── thought_metadata     summary, themes, people, places, and actions
```

This separation matters because derived data can be rebuilt when the model or
chunking strategy changes, and it can be deleted when the user turns AI access
off. The original thought remains intact.

## End-To-End Flow

```text
1. User saves a thought.
2. Backend stores the thought in Postgres.
3. If AI is disabled, the request ends here.
4. If AI is enabled, backend creates a pending background job.
5. RQ places the job in Redis.
6. Worker claims the job and marks the thought as processing.
7. Worker splits the thought into overlapping chunks.
8. Worker sends those chunks to OpenAI's embedding endpoint.
9. Worker sends the thought to OpenAI for structured metadata extraction.
10. Worker stores chunks, vectors, and metadata in Postgres.
11. Worker marks the thought ready for future retrieval.
```

The API does not wait for OpenAI before returning the saved thought. This keeps
capture fast and isolates AI latency or provider failures from the core note-
taking path.

## Durable Job Recovery

Postgres is the durable source of truth for AI jobs; Redis is only the delivery
mechanism. The worker process runs a small reconciliation loop that periodically
looks for:

- pending jobs whose Redis dispatch was lost or whose retry time has arrived;
- running jobs whose worker heartbeat is older than the configured stale-job
  threshold; and
- jobs whose thought was deleted or opted out of AI while they were waiting.

Eligible jobs are selected with database row locks, then re-enqueued with the
same RQ job ID. RQ's atomic unique enqueue prevents concurrent reconcilers from
creating duplicate Redis work. Recovered jobs still pass the normal ownership,
source-hash, AI-consent, rate-limit, and completion checks before OpenAI is
called.

Queue outages leave a job pending with a `not_before` backoff timestamp rather
than permanently failing the user's capture. Provider failures remain failed
and can be explicitly retried through the organization action. A stale-job
recovery may cause a provider call that was already abandoned by a crashed
worker to be attempted again; the database state and source hash prevent stale
results from being committed.

Before claiming processing, the worker checks a per-user AI job allowance.
Limited work remains pending with a `not_before` timestamp and is rescheduled
through RQ. Saving the original thought is not blocked. See
[Request Safety](REQUEST_SAFETY.md) for limits and failure behavior.

The worker also reserves a durable daily organization quota before calling
OpenAI. When the daily allowance is exhausted, the job remains pending until
the next UTC day instead of being marked as a provider failure. Ask and
semantic search reserve their own weighted action units at their API boundary;
the latter can use lexical fallback when its optional semantic allowance is
exhausted.

Organization units are also consumed when AI is re-enabled for a thought, or
when an edited thought is reprocessed, because the thought must be embedded and
organized again.

## Why Chunking Exists

An embedding represents a piece of text as a vector of numbers. Similar meaning
produces vectors that are close together in vector space. A whole thought may
be too long or contain several ideas, so the worker splits it into smaller
windows before embedding it.

The current implementation uses character windows with overlap. The overlap
reduces the chance that an important idea split at a boundary loses context.
This is deliberately simple for the MVP; a token-aware splitter can replace
it later without changing the database contract.

The database uses `pgvector` with 1536 dimensions. The dimension is part of the
schema, so changing the embedding dimensions requires a migration and a
re-embedding plan.

## Why We Store Both Chunks And Vectors

- `chunk_text` is the evidence that can be shown as a citation later.
- `embedding` is used to find semantically related chunks.
- `user_id` is stored on every chunk so every future vector query can enforce
  ownership directly in the database query.
- `chunk_index` preserves the original order.

In the next Ask phase, the question will be embedded using the same embedding
model. A vector similarity query will retrieve the closest chunks belonging to
the current user and only from thoughts with AI participation enabled.

## Why Structured Metadata Extraction Exists

Embeddings help answer semantic questions, but they do not directly provide
structured filters such as themes, people, places, books, or action items. The
metadata extraction call produces a typed schema rather than arbitrary JSON.

The Pydantic model defines the allowed output fields. The OpenAI client uses
structured parsing, and the worker stores the validated result. This is easier
to test and safer to consume than parsing free-form model text.

Deterministic fields such as thought type, manual tags, book fields, and source
type are stored alongside AI metadata. They do not require an OpenAI call.

## Privacy Boundary

`use_with_ask_my_mind` is the policy gate.

When it is `false`, the backend must not:

- enqueue an AI job;
- send the body to OpenAI;
- create chunks or embeddings;
- create AI-generated metadata; or
- make the thought eligible for future retrieval.

When the user changes it from `true` to `false`, the backend deletes the
derived chunks and metadata and cancels pending or running jobs. The thought
itself is not deleted.

The OpenAI API key is used only by the backend worker. It is never sent to the
web or mobile clients and never written to logs.

## Why A Queue Is Used

OpenAI calls are network operations and may be slow or fail temporarily. RQ
separates the user-facing API process from the AI worker:

- API process: validates and saves the thought quickly.
- Redis: holds pending work.
- Worker: performs AI processing and updates job state.
- Postgres: records durable job status and derived data.

The `background_jobs` table is the durable application record. Redis is the
transport mechanism. This distinction means the product can show or audit
processing state without treating Redis as the source of truth.

## Failure Handling

If Redis is unavailable, the thought remains saved and the job stays pending
with retry backoff. If OpenAI fails, the thought remains saved and the job plus
thought status become failed. No raw thought content is written to the error
message or logs.

The worker checks the thought's current AI setting before and after the OpenAI
calls. That prevents a completed job from storing new artifacts after the user
has disabled AI while the job was running.

## Provenance And Safe Reprocessing

Every enrichment job records the schema version, embedding model, metadata
model, and SHA-256 hash of the semantic input it was scheduled to process.
Chunks and metadata copy that provenance and record when processing completed.
The hash lets the worker detect a thought that changed while an OpenAI request
was in flight, so an older result is discarded instead of being attached to
newer content.

Scheduling is idempotent for active work: a second request for the same thought
reuses its pending or running job. A completed job is also safe to deliver more
than once; the worker exits without calling OpenAI again. The existing
`POST /thoughts/{thought_id}/organize` route remains the explicit way to rebuild
derived artifacts after a failure or a model/schema change.

## Interview Explanation

> I implemented an opt-in asynchronous enrichment pipeline. The API persists
> the user thought first, then creates a durable job record and pushes a small
> job reference to Redis through RQ. A worker claims that job, chunks the text,
> generates OpenAI embeddings, and extracts typed metadata using structured
> output. The worker stores the original text, chunks, vectors, and metadata in
> separate tables, with `user_id` on every derived record for tenant isolation.
> The original thought is the source of truth; AI artifacts are rebuildable and
> purgeable. The opt-in flag is enforced before enqueueing, before processing,
> and before committing results, so disabled thoughts are never sent to OpenAI
> and cannot enter retrieval.
