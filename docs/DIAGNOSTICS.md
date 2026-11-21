# Production diagnostics

## Trace a failed action

1. Ask for the `Reference` shown in the error, not the user's thought or prompt.
2. Search Vercel function logs and Render service logs for that UUID.
3. A Vercel `backend_proxy.failed` event distinguishes `connection`, `timeout`,
   and `upstream` failures. A connection failure has no corresponding API event.
4. A Render `http.request` event records the route template, method, status,
   duration, and exception class for unhandled failures. It never records the
   actual path parameters, query, body, credentials, or exception message.
5. `ai.dispatched` links a request reference to a background job UUID. Search
   that job UUID for `ai.ready`, `ai.failed`, or worker events.

The proxy creates a UUID for each request unless it receives a valid UUID.
FastAPI preserves valid UUIDs and replaces invalid references. IDs are for
diagnosis only: they are not credentials, ownership checks, or idempotency keys.
Every API response gets `X-Request-ID`; CORS exposes it to allowed origins.
Successful liveness probes are not logged to avoid unnecessary noise.

Unexpected API errors return a generic `500` with a reference. Proxy connection
failures return `502`; its 60-second upstream timeout returns `504`. Backend
server-error bodies are not forwarded. `Retry-After`, normal admission errors,
pagination headers, and the existing decompression fix are preserved. Nothing
automatically retries a write whose outcome might be uncertain.

## Workers

`worker.finished` means the entry-point invocation returned, not that a pending
or deferred job became ready. Use `ai.ready`, `ai.failed`, and the durable
Postgres job status to determine the AI-processing result. Unexpected worker
exceptions are replaced with a safe error before RQ handles them; raw provider
or SQL exception messages must not be sent to RQ logs. The reconciliation loop
also logs only the exception class, never the traceback or message.

## Deployment

No new credentials, migration, monitoring vendor, or paid service is required.
JSON events go to stderr in the API and worker. The Docker API entry point and
combined staging launcher disable Uvicorn access logs because those logs can
include private search queries. For a custom API start command, use:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log
```

Infrastructure request logs and third-party log retention are separate controls.
Review their query-string capture, access, and retention policies before launch.
Do not enable request-body capture, SQL parameter logging, provider debug logs,
or session replay on private routes. These events are diagnostics, not uptime
alerts or proof that backups can be restored; those remain release checks.
