from app.models import Thought
from app.services.openai_ai import (
    TENTATIVE_EMOTIONS,
    TENTATIVE_THEMES,
    ExtractedThoughtMetadata,
)

THEME_ALIASES = {
    "career": "Work",
    "career development": "Work",
    "professional growth": "Work",
    "self improvement": "Personal growth",
    "self-improvement": "Personal growth",
}

EMOTION_ALIASES = {
    "happy": "Joy",
    "happiness": "Joy",
    "excited": "Excitement",
    "grateful": "Gratitude",
    "thankful": "Gratitude",
    "worried": "Anxiety",
    "anxious": "Anxiety",
    "frustrated": "Frustration",
    "overwhelmed": "Overwhelm",
}


def _normalize_values(
    values: list[str],
    *,
    aliases: dict[str, str] | None = None,
    vocabulary: tuple[str, ...] = (),
    limit: int | None = None,
) -> list[str]:
    canonical_vocabulary = {value.casefold(): value for value in vocabulary}
    normalized: list[str] = []
    seen: set[str] = set()

    for value in values:
        cleaned = " ".join(value.split()).strip()
        if not cleaned:
            continue
        key = cleaned.casefold()
        canonical = (aliases or {}).get(key) or canonical_vocabulary.get(key) or cleaned
        canonical_key = canonical.casefold()
        if canonical_key in seen:
            continue
        normalized.append(canonical)
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
                aliases=THEME_ALIASES,
                vocabulary=TENTATIVE_THEMES,
                limit=5,
            ),
            "emotions": _normalize_values(
                metadata.emotions,
                aliases=EMOTION_ALIASES,
                vocabulary=TENTATIVE_EMOTIONS,
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
