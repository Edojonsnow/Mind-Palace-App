# Account deletion

Users have two explicit choices in Privacy & data:

- `POST /account/deletion` schedules deletion after the configured recovery
  window (60 days by default). `DELETE /account/deletion` cancels it before
  the deadline. Queue dispatch failures leave the committed request pending
  and visible; worker reconciliation dispatches it again.
- `POST /account/deletion/permanent` skips recovery. The strict JSON body is
  `{"confirmation":"DELETE MY ACCOUNT"}`; extra fields are rejected. The API
  deletes only the authenticated account, never an ID supplied by the caller.

Both actions use the existing fail-closed `account_deletion` rate limiter.
Permanent deletion additionally requires a provider-validated session created
within the last 10 minutes (`ACCOUNT_DELETION_RECENT_AUTH_SECONDS`, default 600).
A JWT's issue time is not accepted as proof of recent sign-in. Users with an
older session, or no verified session timestamp, receive 403 and must sign out
and sign in again. Ordinary sign-in and API access are unchanged.

## Configuration and deployment

Apply migration `20261125_0016` before deploying the API. Neon identity deletion
requires these server-only settings for the **same environment/branch** as auth:

- `NEON_API_KEY`: management API key authorized for the project.
- `NEON_PROJECT_ID`: Neon project ID.
- `NEON_AUTH_BRANCH_ID`: branch ID containing this environment's auth users.

Do not put these in the web environment or expose their values to clients.
`GET /account/deletion/options` returns only availability and the recovery
window length. The frontend disables immediate deletion if that check is not
available. Redis admission must be healthy; immediate deletion itself does not
need RQ or an AI provider. A running worker is still needed for scheduled
deletion and for recovering interrupted immediate deletion.

## Completion and failure

The service commits a due-now deletion request before contacting Neon, then
locks the account, deletes the branch's auth identity, and purges owned app
data. Owned thoughts (including deleted/archived notes), embeddings, metadata,
books, collections and memberships, conversations, exports, background-job
records, settings, profile preferences, usage and idempotency records are
removed. Another account's data is untouched.

Only 204 means completion. A provider failure leaves app data and a pending
request intact. If identity deletion succeeds but the local transaction fails,
the pending request remains for worker reconciliation. Neon 404 is accepted on
retry, since the identity might already be removed. Due requests cannot be
cancelled. Failures record exception types only, not provider response bodies.

An irreversible SHA-256 digest of the old auth ID and a deletion timestamp are
retained in `deleted_auth_identities`, without email, raw auth ID or content.
This minimal security revocation record prevents an unexpired old JWT from
recreating the account. It must not be removed as routine user-data cleanup.
Operational/provider backups and already-downloaded exports are outside the
live app purge; deletion does not erase copies a user has downloaded.

After a successful proxied deletion the web clears Neon auth cookies, including
the SDK's local session cache, and reloads to sign-up. A new Neon identity may
reuse the deleted account's email and receives fresh onboarding with AI off.

## Verification

Automated tests use isolated synthetic accounts and mocked Neon admin calls.
They cover confirmation, recent sign-in, rate admission, ownership, complete
purge, old-token rejection, same-email signup, pending failure and worker retry.
They do not delete a real Neon identity. For a manual smoke test use a disposable
account in the development or staging branch, and sign in again immediately
before deletion. Verify both identity and app-data removal, then sign up again
with the same email and confirm onboarding appears.
