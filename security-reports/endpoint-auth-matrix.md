# Endpoint/Auth Matrix

Static inventory from `app/api/routes`.

| Endpoint group | Methods | Auth boundary | Notes |
|---|---|---|---|
| `/health` | GET | Public | Liveness only |
| `/health/db` | GET | Public | Performs a database probe; see MP-SEC-004 |
| `/version` | GET | Public | Returns name, environment, and version |
| `/internal/auth-rate-limit` | POST | Shared secret header | Hidden from OpenAPI; edge restriction recommended |
| `/profile` | GET/PATCH | `CurrentUser` | User-scoped |
| `/profile/ai-preferences` | GET/PATCH | `CurrentUser` | User-scoped |
| `/settings` | GET/PATCH | `CurrentUser` | User-scoped |
| `/settings/ai-usage` | GET | `CurrentUser` | User-scoped |
| `/thoughts` | GET/POST | `CurrentUser` | User-scoped |
| `/thoughts/deleted` | GET | `CurrentUser` | User-scoped recovery view |
| `/thoughts/{thought_id}` | GET/PATCH/DELETE | `CurrentUser` | Ownership predicate present |
| `/thoughts/{thought_id}/organize` | POST | `CurrentUser` | Ownership and rate limit |
| `/thoughts/{thought_id}/restore` | POST | `CurrentUser` | Ownership predicate present |
| `/ask` | POST | `CurrentUser` | Ownership, idempotency, rate limit/quota |
| `/ask/{conversation_id}` | GET | `CurrentUser` | Conversation ownership predicate present |
| `/books` | GET/POST | `CurrentUser` | User-scoped |
| `/exports` | POST | `CurrentUser` | Idempotency and export rate limit |
| `/exports/{export_id}` | GET | `CurrentUser` | Export ownership predicate present |
| `/exports/{export_id}/download` | GET | `CurrentUser` | Export ownership and expiry checks |
| `/account/deletion` | GET/POST/DELETE | `CurrentUser` | User-scoped lifecycle controls |
| `/remember` | GET | `CurrentUser` | User-scoped |

## Auth Review Result

No unauthenticated product mutation or route-ordering bypass was found in the static review. Public system endpoints and the separately protected internal endpoint are the intentional exceptions.
