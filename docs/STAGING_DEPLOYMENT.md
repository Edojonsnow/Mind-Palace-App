# Staging Deployment

This runbook defines the first staging topology for the separate Mind Palace
repositories:

```text
Neon staging branch -> Render free web service (API + worker) -> Render Key Value
                                                        ^
Vercel staging web -------------------------------------+
```

The Blueprint in `render.yaml` creates one free staging web service containing
the API and RQ worker, plus a free Render Key Value resource. It does not
contain credentials. Render's `sync: false` entries must be filled during the
initial Blueprint setup, and later secret changes must be made in the Render
dashboard or an environment group.

This combined API/worker topology is a temporary staging arrangement to avoid
paid worker compute. The service shares CPU and memory, sleeps after
inactivity, and stops both processes together. Production should use separate
API and worker services.

## 1. Prepare Neon

Use the existing Neon staging branch and collect these values without placing
them in Git:

- `DATABASE_URL`
- `NEON_AUTH_JWKS_URL`
- `NEON_AUTH_ISSUER`
- `NEON_AUTH_AUDIENCE`
- `NEON_AUTH_BASE_URL`
- `NEON_API_KEY`, `NEON_PROJECT_ID`, and `NEON_AUTH_BRANCH_ID` for account-deletion testing

The backend and Neon Auth values must refer to the same staging branch. The
issuer is the auth host origin; the base URL includes `/neondb/auth`.
`NEON_AUTH_AUDIENCE` must be the `aud` claim from a real Neon Auth JWT. The
opaque session token sent by the browser is not a JWT and cannot provide this
value. The web client obtains the JWT through Neon's JWT-specific client method;
decode it locally and store only the audience claim in Render.

## 2. Create the Render staging Blueprint

1. Open Render and create a Blueprint from the backend repository.
2. Select the branch intended for staging and use `render.yaml` at the repository root.
3. Provide the `sync: false` values when Render asks for them.
4. Set `BACKEND_CORS_ORIGINS` to the final Vercel staging origin. Do not use `*`.
5. Confirm the Key Value instance has no external IP allow-list entries. The
   combined service should use its internal connection string.
6. The free service runs `alembic upgrade head` during startup before launching
   the API and worker. This replaces Render's paid-only pre-deploy command.

Render's `/health` check is intentionally public and does not touch Postgres.
The protected `/health/db` endpoint is for trusted monitoring only and requires
`X-Health-Check-Token`.

## 3. Configure Vercel staging

Use the web repository's `.env.staging.example` as the variable checklist.
Configure the values in Vercel's Preview environment or a custom staging
environment, never in browser-exposed variables unless the value is the public
API origin.

Required web values:

- `NEXT_PUBLIC_API_BASE_URL`: Render staging API URL
- `NEON_AUTH_BASE_URL`: Neon Auth base URL for the staging branch
- `NEON_AUTH_COOKIE_SECRET`: a new stable secret used only by staging
- `AUTH_RATE_LIMITS_ENABLED=true`
- `AUTH_RATE_LIMIT_API_URL`: Render staging API URL
- `AUTH_RATE_LIMIT_TOKEN`: exactly the same secret as the Render API value

Set the Vercel staging origin in Render's `BACKEND_CORS_ORIGINS` and redeploy
the API after changing it.

## 4. Run the staging smoke test

Use a disposable staging account and test in this order:

1. `GET /health` returns `200` from the Render API.
2. The web app loads and sign-up, confirmation, sign-in, and sign-out work.
3. Save a thought with AI disabled; verify it remains available in Recall.
4. Save a separate AI-enabled thought; verify the co-located worker creates its derived artifacts.
5. Ask My Mind returns citations from the staging user's thoughts.
6. Keyword Recall does not consume semantic-search quota; semantic Recall reports
   its effective mode and fallback behavior.
7. Edit, archive, restore, export, and account-deletion recovery work.
8. The API and worker logs contain no thought bodies, prompts, responses, tokens,
   or database URLs.

Do not run staging migrations from a local `.env` unless the target is confirmed
to be the staging branch. The Render startup supervisor is the normal migration
path for this free environment.

## 5. Production boundary

Staging and production must use different Neon branches, Neon Auth branches,
Render resources, Redis instances, Vercel environment values, and cookie
secrets. Do not promote staging secrets or the staging database URL into
production.

References:

- [Render Blueprints](https://render.com/docs/infrastructure-as-code)
- [Render health checks](https://render.com/docs/health-checks)
- [Render private networking](https://render.com/docs/private-network)
- [Vercel environments](https://vercel.com/docs/deployments/environments)
