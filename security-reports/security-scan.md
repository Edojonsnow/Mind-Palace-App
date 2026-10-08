# Mind Palace Backend Security Scan

Date: 2026-10-09
Scope: static review of `mind-palace-app` FastAPI routes, auth boundary, request/response schemas, ownership queries, rate limiting, logging, and container defaults.

## Executive Summary

No confirmed Critical or High severity vulnerability was found in this static pass. Product routes consistently use the authenticated application-user dependency, ownership predicates are present on user-owned reads and writes, request schemas are explicit, and no user-controlled raw SQL or shell execution was found.

The main risks are availability and production-hardening issues: unbounded thought payloads, per-request external work in authentication, a publicly reachable database health probe, a bearer-protected internal rate-limit endpoint, broad CORS method/header allowances, optional audience validation, and an unverified dependency CVE status.

## Findings

### MP-SEC-001: Thought body and manual tag collections are unbounded

- Severity: Medium
- References: `app/schemas/thought.py:12`, `app/schemas/thought.py:22`, `app/schemas/thought.py:30`, `app/schemas/thought.py:42`; `app/services/thoughts.py:26-35`
- Impact: An authenticated caller can submit very large thought bodies or very large/long tag lists. AI-enabled thoughts have a separate AI size check, but AI-disabled thoughts do not. This can increase database/storage usage, response sizes, indexing work, and downstream processing cost.
- Recommendation: Add an explicit maximum body size for every thought, plus per-tag and total-tag-count limits. Enforce the same limits on create and update, independent of AI eligibility.

### MP-SEC-002: Authentication depends on network work on the request path

- Severity: Medium (availability/performance)
- References: `app/core/auth.py:36-45`, `app/core/auth.py:109-119`, `app/core/auth.py:166-180`
- Impact: JWT verification creates a new `PyJWKClient` per request, and opaque/session-token fallback makes an outbound Neon Auth request. Under load or upstream degradation, authentication can become a bottleneck or an availability amplifier. This is not an identified token-bypass issue.
- Recommendation: Reuse a bounded JWK client/cache, set explicit connection/read limits, instrument failure rates, and use a controlled circuit-breaker/failure policy for session validation. Confirm the Neon Auth token path used in production so opaque fallback is only used when required.

### MP-SEC-003: Internal auth-rate-limit endpoint is bearer-token protected but network reachable

- Severity: Medium (defense in depth)
- References: `app/api/routes/internal.py:12-34`
- Impact: The endpoint correctly uses a secret token and constant-time comparison, but a leaked long-lived shared token lets a caller invoke admission checks directly and potentially weaken auth-abuse protection. It is hidden from OpenAPI, which is not an access control.
- Recommendation: Restrict the route at the network/edge layer to the trusted web service where possible, rotate the token, keep it in a secret manager, and consider a signed short-lived service credential or mTLS if the deployment platform supports it.

### MP-SEC-004: Unauthenticated database health probe can amplify load

- Severity: Low/Medium
- References: `app/api/routes/health.py:16-27`
- Impact: Any caller can force a database connection/query through `/health/db`. Repeated probing can consume connection-pool capacity and also confirms database reachability.
- Recommendation: Keep `/health` public for liveness, but restrict `/health/db` to the platform health-check identity/private network or apply a tight edge rate limit and a cached readiness result.

### MP-SEC-005: Production security-header and CORS hardening is incomplete

- Severity: Low/Medium
- References: `app/main.py:24-40`
- Impact: CORS uses explicit origins, which avoids the dangerous wildcard-plus-credentials combination, but methods and headers are both wildcarded. No application or documented edge configuration was found for HSTS, `X-Content-Type-Options`, `Referrer-Policy`, or host/HTTPS enforcement.
- Recommendation: Narrow methods/headers to the actual contract and verify production origins exclude local development origins. Configure HSTS, `X-Content-Type-Options`, `Referrer-Policy`, trusted-host handling, and HTTPS enforcement at the application or Render edge.

### MP-SEC-006: JWT audience validation is optional by configuration

- Severity: Low/Medium
- References: `app/core/config.py:17-20`; `app/core/auth.py:38-45`
- Impact: When `NEON_AUTH_AUDIENCE` is unset, audience verification is disabled. Issuer, signature, and subject checks still apply, so this is a deployment-hardening risk rather than a confirmed bypass.
- Recommendation: Require and validate the expected audience in staging and production, or make the disabled-audience mode an explicit local-development-only setting.

### MP-SEC-007: Dependency vulnerability status is unverified

- Severity: Unrated verification gap
- References: `pyproject.toml:11-24`
- Impact: Dependencies use minimum-version ranges and no lockfile was found in the backend repository. `pip-audit` and `safety` are not installed, so current transitive CVE status was not established.
- Recommendation: Generate a locked deployment dependency set and run `pip-audit` (or an equivalent OSV/SCA scanner) in CI and before production releases.

### MP-SEC-008: Container defaults need production hardening

- Severity: Low
- References: `Dockerfile:1-17`; `compose.yaml:1-26`
- Impact: The image runs as root, uses a floating `python:3.12-slim` tag, and has no container healthcheck. The compose Redis service is intentionally local and unauthenticated; it must not be treated as the production Redis posture.
- Recommendation: Use a non-root user, pin the base image by digest or controlled release, add a healthcheck, and use managed/private Redis with authentication and TLS in production.

### MP-SEC-009: General authenticated mutation rate limits are incomplete

- Severity: Low/Medium
- References: `app/api/routes/thoughts.py:31-42`, `app/api/routes/thoughts.py:166-183`, `app/api/routes/books.py:21-28`, `app/api/routes/profile.py:20-22`, `app/api/routes/settings.py:24-29`; `app/core/rate_limit.py:57-69`
- Impact: The current limiter covers Ask, semantic search, organization retry, exports, and background AI processing, but ordinary authenticated writes are not generally rate-limited. A compromised valid session could therefore generate high-volume thought/book/profile/settings traffic and consume database resources.
- Recommendation: Add low-cost per-user mutation limits, with separate policies for thought writes and account/profile settings. Keep limits generous enough for normal use and return `429` with `Retry-After`.

## Controls That Passed Static Review

- Authenticated product routes use `CurrentUser`; no unauthenticated product mutation was found.
- Thought, book, conversation, export, and metadata queries include authenticated-user ownership predicates.
- Request models explicitly list writable fields; no direct `**request_body` ORM update was found.
- Profile and AI-preference schemas reject unknown fields. `UserSettingsUpdate` should also use `extra="forbid"` for consistency, although the service currently updates only known declared fields.
- Query parameters have length/range validation, and SQLAlchemy bind parameters plus escaped `LIKE` patterns are used for recall/search.
- Logs reviewed do not include thought bodies, chat messages, prompts, AI responses, access tokens, or database URLs.
- Rate limiting and quota checks protect Ask, semantic search, organization retry, exports, and background AI processing. Auth abuse admission is implemented through the shared-token internal endpoint.

## Verification Gaps

- No live staging dynamic scan with ZAP, Burp, or equivalent was run.
- No dependency CVE database scan was run because the supported scanner tools are unavailable locally.
- Reverse-proxy behavior for forwarded client-IP headers and production CORS/HTTPS/security headers must be verified on Render/Vercel configuration, not inferred from the FastAPI source alone.

## Recommended Order

1. Bound thought bodies and manual tags.
2. Harden/cache the auth verification path and require production audience validation.
3. Restrict the internal auth-rate-limit and database health endpoints at the edge.
4. Add dependency scanning/locking and container hardening to the release pipeline.
