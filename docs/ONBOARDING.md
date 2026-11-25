# New-user onboarding

New accounts start with a short privacy introduction and a first-thought step.
The existing `GET /settings` response returns `onboarding_step` and
`onboarding_completed_at`; no additional initial request is required.

`PATCH /settings/onboarding` accepts only `{"action": "continue"}` or
`{"action": "skip"}`. Progress is authenticated, rate-limited through
`settings_write`, and persisted per account. Repeated requests do not reopen
completed onboarding or replace its completion timestamp. This endpoint cannot
change AI consent or personalization settings.

The first successful thought creation completes onboarding in the thought's
transaction. Failed creation does not complete it. No AI provider key,
personalization, or background job is required; existing request-admission
rules still apply. Users may skip and explore, or skip to
the existing Profile workspace. Closing the thought composer preserves setup.
Onboarding state is included in exports and removed with user settings during
account deletion. No analytics or session recording is added.

## Deployment

Apply migration `20261121_0015` before deploying the web client. The migration
exempts all existing settings rows so returning users are not interrupted.
Only settings rows created afterward start with incomplete onboarding. New
fields are additive; older clients can ignore them. The web client does not
show setup if it receives an older response without onboarding fields.

This work preserves the current app design and does not rename existing
routes, add billing or image uploads, or claim end-to-end encryption.
