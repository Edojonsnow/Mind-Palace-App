import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.queue import enqueue_ai_processing
from app.models import (
    AIProcessingStatus,
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
)
from app.services.openai_ai import (
    TENTATIVE_EMOTIONS,
    TENTATIVE_THEMES,
    ExtractedThoughtMetadata,
    OpenAIProvider,
)

logger = logging.getLogger(__name__)


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


def _set_job_failed(db: Session, job_id: UUID, thought_id: UUID, error: Exception) -> None:
    job = db.get(BackgroundJob, job_id)
    thought = db.get(Thought, thought_id)
    if job is None:
        return

    job.status = BackgroundJobStatus.FAILED.value
    job.error_message = type(error).__name__
    job.completed_at = datetime.now(UTC)
    if thought is not None and thought.use_with_ask_my_mind:
        thought.ai_processing_status = AIProcessingStatus.FAILED.value
    db.commit()


def schedule_ai_processing(db: Session, thought: Thought) -> BackgroundJob:
    job = BackgroundJob(
        user_id=thought.user_id,
        thought_id=thought.id,
        job_type=BackgroundJobType.CHUNK_THOUGHT.value,
        status=BackgroundJobStatus.PENDING.value,
        attempt_count=0,
    )
    thought.ai_processing_status = AIProcessingStatus.PENDING.value
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        enqueue_ai_processing(job.id, thought.id)
    except Exception as error:
        logger.warning("Unable to enqueue AI processing job: %s", type(error).__name__)
        _set_job_failed(db, job.id, thought.id, error)

    db.refresh(job)
    return job


def purge_ai_artifacts(db: Session, thought: Thought, *, commit: bool = True) -> None:
    db.execute(delete(ThoughtChunk).where(ThoughtChunk.thought_id == thought.id))
    db.execute(delete(ThoughtMetadata).where(ThoughtMetadata.thought_id == thought.id))
    db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.thought_id == thought.id,
            BackgroundJob.status.in_(
                [BackgroundJobStatus.PENDING.value, BackgroundJobStatus.RUNNING.value]
            ),
        )
        .values(
            status=BackgroundJobStatus.CANCELLED.value,
            completed_at=datetime.now(UTC),
        )
    )
    thought.ai_processing_status = AIProcessingStatus.NOT_REQUESTED.value
    if commit:
        db.commit()


def _store_metadata(
    db: Session,
    thought: Thought,
    metadata: ExtractedThoughtMetadata,
) -> None:
    metadata = normalize_extracted_metadata(metadata)
    db.add(
        ThoughtMetadata(
            user_id=thought.user_id,
            thought_id=thought.id,
            summary=metadata.summary,
            themes=metadata.themes,
            emotions=metadata.emotions,
            people=metadata.people,
            places=metadata.places,
            books=metadata.books,
            key_questions=metadata.key_questions,
            action_items=metadata.action_items,
            deterministic_metadata=deterministic_metadata(thought),
        )
    )


def process_ai_job(
    db: Session,
    job_id: UUID,
    thought_id: UUID,
    provider_factory: Callable[[], OpenAIProvider] = OpenAIProvider,
) -> None:
    job = db.get(BackgroundJob, job_id)
    thought = db.get(Thought, thought_id)
    if job is None or thought is None:
        return

    if thought.deleted_at is not None or not thought.use_with_ask_my_mind:
        job.status = BackgroundJobStatus.CANCELLED.value
        job.completed_at = datetime.now(UTC)
        purge_ai_artifacts(db, thought, commit=False)
        db.commit()
        return

    job.status = BackgroundJobStatus.RUNNING.value
    job.attempt_count += 1
    job.started_at = datetime.now(UTC)
    thought.ai_processing_status = AIProcessingStatus.PROCESSING.value
    db.commit()

    try:
        provider = provider_factory()
        chunks = chunk_text(
            thought.body,
            settings.ai_chunk_size_chars,
            settings.ai_chunk_overlap_chars,
        )
        embeddings = provider.embed(chunks)
        metadata = provider.extract_metadata(thought.body)

        db.refresh(thought)
        if thought.deleted_at is not None or not thought.use_with_ask_my_mind:
            job.status = BackgroundJobStatus.CANCELLED.value
            job.completed_at = datetime.now(UTC)
            purge_ai_artifacts(db, thought, commit=False)
            db.commit()
            return

        db.execute(delete(ThoughtChunk).where(ThoughtChunk.thought_id == thought.id))
        db.execute(delete(ThoughtMetadata).where(ThoughtMetadata.thought_id == thought.id))
        for index, (chunk, embedding) in enumerate(zip(chunks, embeddings, strict=True)):
            db.add(
                ThoughtChunk(
                    user_id=thought.user_id,
                    thought_id=thought.id,
                    chunk_text=chunk,
                    chunk_index=index,
                    embedding=embedding,
                )
            )
        _store_metadata(db, thought, metadata)
        thought.ai_processing_status = AIProcessingStatus.READY.value
        job.status = BackgroundJobStatus.COMPLETED.value
        job.completed_at = datetime.now(UTC)
        db.commit()
    except Exception as error:
        db.rollback()
        _set_job_failed(db, job_id, thought_id, error)
