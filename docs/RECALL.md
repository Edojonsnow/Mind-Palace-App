# Recall

Recall is the deterministic thought-browsing and search capability. It is
separate from Ask My Mind: Recall retrieves saved thought records, while Ask
My Mind uses eligible AI-processed chunks to answer a question.

## Endpoint

```text
GET /thoughts
Authorization: Bearer <neon-auth-access-token>
```

The response remains a JSON array of `ThoughtRead` objects so existing web and
mobile clients do not need a response-shape migration.

## Query Parameters

| Parameter | Meaning |
| --- | --- |
| `q` | Case-insensitive substring search across title, body, source title, source author, book title, and book author. |
| `thought_type` | Exact type: `thought`, `journal`, `quote`, or `book_excerpt`. |
| `source_type` | Exact source: `manual`, `book`, `article`, `website`, `audio`, `import`, or `unknown`. |
| `tag` | Exact manual tag match. |
| `book` | Case-insensitive substring search across book title and book author. |
| `is_archived` | Restrict results to `true` or `false`; omitted means both. |
| `created_from` | Inclusive ISO 8601 lower timestamp bound. |
| `created_to` | Inclusive ISO 8601 upper timestamp bound. |
| `page` | One-based page number; default `1`. |
| `page_size` | Number of results from `1` to `100`; default `20`. |

Every query is scoped to the authenticated user and excludes soft-deleted
thoughts. Results are ordered by `created_at DESC, id DESC` so repeated
requests have a stable order even when timestamps tie.

## Pagination

The response body is the requested page. Pagination metadata is returned in
headers that are exposed through CORS:

```text
X-Total-Count: 42
X-Page: 1
X-Page-Size: 20
X-Total-Pages: 3
```

Example:

```text
GET /thoughts?q=focus&tag=work&is_archived=false&page=1&page_size=20
```

## Implementation Boundary

The MVP uses PostgreSQL case-insensitive substring matching and a JSON tag
match. The composite index covers the ownership, deletion, archive, and
created-at portions of the query. If the dataset grows, the next switch is
PostgreSQL full-text search for `q`, followed by a GIN index or a dedicated
search service only if measured query latency requires it.
