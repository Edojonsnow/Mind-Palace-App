from app.models import Thought
from app.services.openai_ai import ExtractedThoughtMetadata


def _normalize_values(
    values: list[str],
    *,
    limit: int | None = None,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            continue
        canonical_key = cleaned.casefold()
        if canonical_key in seen:
            continue
        normalized.append(cleaned)
        seen.add(canonical_key)
        if limit is not None and len(normalized) >= limit:
            break

    return normalized


def normalize_extracted_metadata(metadata: ExtractedThoughtMetadata) -> ExtractedThoughtMetadata:
    """Keep AI metadata compact and stable before persisting it."""
    return metadata.model_copy(
        update={
            "themes": _normalize_values(
                metadata.themes,
                limit=5,
            ),
            "emotions": _normalize_values(
                metadata.emotions,
                limit=5,
            ),
            "people": _normalize_values(metadata.people),
            "places": _normalize_values(metadata.places),
            "books": _normalize_values(metadata.books),
            "key_questions": _normalize_values(metadata.key_questions),
            "action_items": _normalize_values(metadata.action_items),
        }
    )


def chunk_text(text: str, chunk_size: int, overlap: int) -> list[str]:
    """Split text into overlapping windows while preferring whitespace boundaries."""
    if chunk_size <= overlap:
        raise ValueError("Chunk size must be greater than overlap")

    chunks: list[str] = []
    start = 0
    while start < len(text):
        proposed_end = min(start + chunk_size, len(text))
        end = proposed_end
        if proposed_end < len(text):
            boundary = text.rfind(" ", start, proposed_end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break
        start = max(end - overlap, start + 1)

    return chunks


def semantic_text(thought: Thought) -> str:
    """Build the private semantic representation used for AI enrichment."""
    sections: list[str] = []

    def add_section(label: str, value: object) -> None:
        if isinstance(value, list):
            cleaned = [" ".join(str(item).split()).strip() for item in value if str(item).strip()]
            value = ", ".join(cleaned)
        if value is None:
            return
        cleaned_value = " ".join(str(value).split()).strip()
        if cleaned_value:
            sections.append(f"{label}: {cleaned_value}")

    add_section("Title", thought.title)
    add_section("Thought", thought.body)
    add_section("Source type", thought.source_type)
    add_section("Source title", thought.source_title)
    add_section("Source author", thought.source_author)
    add_section("Book", thought.book_title)
    add_section("Book author", thought.book_author)
    add_section("Page", thought.page_reference)
    add_section("Tags", thought.manual_tags)
    return "\n".join(sections)


def deterministic_metadata(thought: Thought) -> dict[str, object]:
    return {
        "thought_type": thought.thought_type,
        "source_type": thought.source_type,
        "manual_tags": thought.manual_tags,
        "book_title": thought.book_title,
        "book_author": thought.book_author,
        "page_reference": thought.page_reference,
        "created_at": thought.created_at.isoformat() if thought.created_at else None,
    }
