from datetime import UTC, datetime

from app.core.config import settings
from app.schemas.ask import AskSource
from app.services.ask_retrieval import RetrievedChunk

NO_SOURCE_ANSWER = "I could not find an AI-enabled thought that answers that question yet."


def no_source_answer() -> str:
    return NO_SOURCE_ANSWER


def build_context(retrieved_chunks: list[RetrievedChunk]) -> str:
    sections: list[str] = []
    remaining = settings.ask_max_context_chars
    for index, retrieved in enumerate(retrieved_chunks, start=1):
        if remaining <= 0:
            break
        label = f"S{index}"
        title = retrieved.thought.title or "Untitled thought"
        text = retrieved.chunk.chunk_text[:remaining]
        sections.append(f"[{label}] {title}\n{text}")
        remaining -= len(text)
    return "\n\n".join(sections)


def build_sources(
    retrieved_chunks: list[RetrievedChunk],
    cited_labels: set[str],
) -> list[AskSource]:
    return [
        AskSource(
            citation_label=f"S{index}",
            chunk_id=retrieved.chunk.id,
            thought_id=retrieved.thought.id,
            title=retrieved.thought.title,
            snippet=retrieved.chunk.chunk_text,
            source_type=retrieved.thought.source_type,
            source_title=retrieved.thought.source_title or retrieved.thought.book_title,
            source_author=retrieved.thought.source_author or retrieved.thought.book_author,
            created_at=retrieved.thought.created_at or datetime.now(UTC),
            similarity_score=retrieved.similarity_score,
            is_cited=f"S{index}" in cited_labels,
        )
        for index, retrieved in enumerate(retrieved_chunks, start=1)
    ]
