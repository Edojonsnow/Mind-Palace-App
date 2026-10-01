import logging
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
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
    AI_ENRICHMENT_SCHEMA_VERSION,
    chunk_text,
    deterministic_metadata,
    enrichment_source_hash,
    normalize_extracted_metadata,
    semantic_text,
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
    active_job = db.scalar(
        select(BackgroundJob)
        .where(
            BackgroundJob.thought_id == thought.id,
            BackgroundJob.job_type == BackgroundJobType.CHUNK_THOUGHT.value,
            BackgroundJob.status.in_(
                [BackgroundJobStatus.PENDING.value, BackgroundJobStatus.RUNNING.value]
            ),
        )
        .order_by(BackgroundJob.created_at.desc())
    )
    if active_job is not None:
        return active_job

    job = BackgroundJob(
        user_id=thought.user_id,
        thought_id=thought.id,
        job_type=BackgroundJobType.CHUNK_THOUGHT.value,
        status=BackgroundJobStatus.PENDING.value,
        attempt_count=0,
        enrichment_schema_version=AI_ENRICHMENT_SCHEMA_VERSION,
        embedding_model=settings.openai_embedding_model,
        metadata_model=settings.openai_metadata_model,
        source_hash=enrichment_source_hash(thought),
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
    *,
    enrichment_schema_version: int,
    metadata_model: str,
    source_hash: str,
    processed_at: datetime,
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
            enrichment_schema_version=enrichment_schema_version,
            metadata_model=metadata_model,
            source_hash=source_hash,
            processed_at=processed_at,
        )
    )


def process_ai_job(
    db: Session,
    job_id: UUID,
    thought_id: UUID,
    provider_factory: Callable[[], OpenAIProvider] = OpenAIProvider,
) -> None:
    job = db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.id == job_id)
        .with_for_update()
    )
    thought = db.get(Thought, thought_id)
    if job is None or thought is None:
        return

    if job.status in {
        BackgroundJobStatus.COMPLETED.value, BackgroundJobStatus.CANCELLED.value,
        BackgroundJobStatus.RUNNING.value,
    }:
        return

    source_hash = job.source_hash or enrichment_source_hash(thought)
    if job.enrichment_schema_version is None:
        job.enrichment_schema_version = AI_ENRICHMENT_SCHEMA_VERSION
    if job.embedding_model is None:
        job.embedding_model = settings.openai_embedding_model
    if job.metadata_model is None:
        job.metadata_model = settings.openai_metadata_model
    if job.source_hash is None:
        job.source_hash = source_hash
    assert job.enrichment_schema_version is not None
    assert job.embedding_model is not None
    assert job.metadata_model is not None

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
        enrichment_text = semantic_text(thought)
        chunks = chunk_text(
            enrichment_text,
            settings.ai_chunk_size_chars,
            settings.ai_chunk_overlap_chars,
        )
        embeddings = provider.embed(chunks)
        metadata = provider.extract_metadata(enrichment_text)

        db.refresh(thought)
        db.refresh(job)
        current_source_hash = enrichment_source_hash(thought)
        if (
            job.status != BackgroundJobStatus.RUNNING.value
            or thought.deleted_at is not None
            or not thought.use_with_ask_my_mind
            or current_source_hash != source_hash
        ):
            if job.status == BackgroundJobStatus.RUNNING.value:
                job.status = BackgroundJobStatus.CANCELLED.value
                job.completed_at = datetime.now(UTC)
            db.commit()
            return

        processed_at = datetime.now(UTC)
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
                    enrichment_schema_version=job.enrichment_schema_version,
                    embedding_model=job.embedding_model,
                    source_hash=source_hash,
                )
            )
        _store_metadata(
            db,
            thought,
            metadata,
            enrichment_schema_version=job.enrichment_schema_version,
            metadata_model=job.metadata_model,
            source_hash=source_hash,
            processed_at=processed_at,
        )
        thought.ai_processing_status = AIProcessingStatus.READY.value
        job.status = BackgroundJobStatus.COMPLETED.value
        job.completed_at = processed_at
        db.commit()
    except Exception as error:
        db.rollback()
        _set_job_failed(db, job_id, thought_id, error)
