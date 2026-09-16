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
from app.services.ai_processing_content import (
    chunk_text,
    deterministic_metadata,
    normalize_extracted_metadata,
)
from app.services.openai_ai import ExtractedThoughtMetadata, OpenAIProvider

logger = logging.getLogger(__name__)


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
