# Ask My Mind

## MVP Contract

Ask My Mind accepts a question from an authenticated user and answers from
that user's eligible thoughts. It does not search the public web yet.

```text
POST /ask
{
  "question": "What did I say about focused work?",
  "conversation_id": null
}
```

The response contains an answer, a conversation ID, and the retrieved thought
chunks that can be displayed as sources in the web or mobile client.

```text
{
  "conversation_id": "...",
  "answer": "You said focused work matters ... [S1]",
  "sources": [
    {
      "citation_label": "S1",
      "thought_id": "...",
      "chunk_id": "...",
      "snippet": "...",
      "similarity_score": 0.82,
      "is_cited": true
    }
  ]
}
```

## Request Flow

```text
1. Authenticate the request with Neon Auth.
2. Resolve the application user from the auth subject.
3. Load or create the conversation when chat history is enabled.
4. Persist the user's question before calling OpenAI.
5. Confirm that eligible, ready thought chunks exist.
6. Embed the question with the same model used for thought chunks.
7. Search pgvector for the closest chunks.
8. Enforce user ownership and AI participation in the database query.
9. Build a bounded context using labels such as [S1] and [S2].
10. Ask OpenAI for a structured answer and citation labels.
11. Validate citation labels against the retrieved source list.
12. Persist the assistant response and source metadata.
13. Return the answer and sources to the client.
```

The original thought is never replaced by the generated answer. The answer is
chat output, while the thought and its chunks remain the source records.

## Retrieval

The question is embedded with `text-embedding-3-small`, producing the same
1536-dimensional vector shape used by `thought_chunks.embedding`.

In Neon, the service uses pgvector's cosine distance operator and returns the
top configured results. The query filters on all of these conditions:

- the chunk belongs to the authenticated user;
- the parent thought belongs to the authenticated user;
- `use_with_ask_my_mind` is true;
- the thought status is `ready`;
- the thought and chunk are not deleted; and
- the thought is not archived.

The repeated ownership checks are intentional defense in depth. A future
optimization can add an HNSW index when the number of chunks justifies it. The
MVP uses a direct pgvector query to minimize operational complexity.

## Answer Generation

The worker already generates the searchable thought chunks. Ask My Mind uses a
separate synchronous request for the question because the client is waiting
for an answer.

The model receives:

- a system instruction to answer only from supplied personal sources;
- a bounded number of previous chat messages; and
- labeled retrieved chunks.

The response is parsed into a Pydantic model containing:

- `answer`;
- `citation_ids`, such as `S1` and `S2`.

The API ignores citation labels that were not present in the retrieved source
list. This prevents the model from inventing a source identifier. The client
can display all retrieved sources while highlighting the sources explicitly
referenced by the model.

If no eligible thoughts exist, the API returns a clear no-source answer and
does not call OpenAI for answer generation.

## Chat History

Chat history is stored by default in:

- `chat_conversations` for the user-owned conversation;
- `chat_messages` for user and assistant messages; and
- `chat_messages.citations` for the assistant's source payload.

The next request in the same conversation receives a bounded history window
for continuity. The `store_chat_history` setting is respected. When disabled,
the request can still answer from eligible thoughts, but no conversation or
message records are written.

The API does not log question text, assistant text, retrieved chunks, or
prompts.

## Current Boundaries

This implementation does not yet include:

- web search citations;
- streaming responses;
- conversation deletion;
- conversation title generation;
- reranking beyond cosine similarity; or
- mobile offline chat behavior.

Those are separate product decisions and should not be mixed into the first
working retrieval path.

## Interview Explanation

> I built retrieval-augmented generation over user-owned notes. The question
> is embedded with the same embedding model used during ingestion, then a
> pgvector cosine-distance query retrieves only ready chunks belonging to the
> authenticated user and explicitly enabled for AI. I label those chunks in a
> bounded prompt and request a structured answer containing citation labels.
> The API validates those labels against the actual retrieved rows before
> returning sources. Chat messages are stored separately from notes so the
> original thought remains the source of truth, while the conversation can
> maintain continuity through a bounded history window.
