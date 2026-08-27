import logging
from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.models import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    ChatMessage,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
    User,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def list_deleted_thoughts(db: Session, user: User) -> list[Thought]:
    now = utc_now()
    return list(
        db.scalars(
            select(Thought)
            .where(
                Thought.user_id == user.id,
                Thought.deleted_at.is_not(None),
                Thought.purge_at > now,
            )
            .order_by(Thought.deleted_at.desc(), Thought.id.desc())
        )
    )


def restore_thought(db: Session, user: User, thought_id: UUID) -> Thought:
    thought = db.scalar(
        select(Thought).where(
            Thought.id == thought_id,
            Thought.user_id == user.id,
            Thought.deleted_at.is_not(None),
        )
    )
    if thought is None or thought.purge_at is None or as_utc(thought.purge_at) <= utc_now():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thought not found")

    thought.deleted_at = None
    thought.purge_at = None
    db.execute(
        update(BackgroundJob)
        .where(
            BackgroundJob.thought_id == thought.id,
            BackgroundJob.job_type == BackgroundJobType.PURGE_DELETED_THOUGHT.value,
            BackgroundJob.status.in_(
                [BackgroundJobStatus.PENDING.value, BackgroundJobStatus.RUNNING.value]
            ),
        )
        .values(
            status=BackgroundJobStatus.CANCELLED.value,
            completed_at=utc_now(),
        )
    )
    db.commit()
    db.refresh(thought)
    return thought


def schedule_thought_purge(db: Session, thought: Thought) -> None:
    job = BackgroundJob(
        user_id=thought.user_id,
        thought_id=thought.id,
        job_type=BackgroundJobType.PURGE_DELETED_THOUGHT.value,
        status=BackgroundJobStatus.PENDING.value,
        attempt_count=0,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        from app.core.queue import enqueue_thought_purge

        enqueue_thought_purge(job.id, thought.id, thought.purge_at)
    except Exception as error:
        logger.warning("Unable to schedule thought purge: error_type=%s", type(error).__name__)
        job.status = BackgroundJobStatus.FAILED.value
        job.error_message = type(error).__name__
        db.commit()


def _scrub_thought_citations(
    db: Session,
    thought: Thought,
    chunk_ids: set[str],
) -> None:
    thought_id = str(thought.id)
    for message in db.scalars(
        select(ChatMessage).where(ChatMessage.user_id == thought.user_id)
    ):
        citations = message.citations or []
        filtered = [
            citation
            for citation in citations
            if str(citation.get("thought_id")) != thought_id
            and str(citation.get("chunk_id")) not in chunk_ids
        ]
        if len(filtered) != len(citations):
            message.citations = filtered


def permanently_purge_thought(
    db: Session,
    thought: Thought,
    *,
    keep_job_id: UUID | None = None,
) -> None:
    chunk_ids = {str(chunk_id) for chunk_id in db.scalars(
        select(ThoughtChunk.id).where(ThoughtChunk.thought_id == thought.id)
    )}
    _scrub_thought_citations(db, thought, chunk_ids)
    db.execute(delete(ThoughtChunk).where(ThoughtChunk.thought_id == thought.id))
    db.execute(delete(ThoughtMetadata).where(ThoughtMetadata.thought_id == thought.id))
    job_filters = [BackgroundJob.thought_id == thought.id]
    if keep_job_id is not None:
        job_filters.append(BackgroundJob.id != keep_job_id)
    db.execute(delete(BackgroundJob).where(*job_filters))
    if keep_job_id is not None:
        job = db.get(BackgroundJob, keep_job_id)
        if job is not None:
            job.thought_id = None
    db.delete(thought)


def process_thought_purge(db: Session, job_id: UUID, thought_id: UUID) -> None:
    job = db.get(BackgroundJob, job_id)
    thought = db.get(Thought, thought_id)
    if job is None or thought is None:
        return

    if thought.deleted_at is None:
        job.status = BackgroundJobStatus.CANCELLED.value
        job.completed_at = utc_now()
        db.commit()
        return

    if thought.purge_at is None or as_utc(thought.purge_at) > utc_now():
        return

    job.status = BackgroundJobStatus.RUNNING.value
    job.attempt_count += 1
    db.flush()
    permanently_purge_thought(db, thought, keep_job_id=job.id)
    job.status = BackgroundJobStatus.COMPLETED.value
    job.completed_at = utc_now()
    db.commit()


def purge_expired_thoughts(db: Session) -> int:
    expired = list(
        db.scalars(
            select(Thought).where(
                Thought.deleted_at.is_not(None),
                Thought.purge_at.is_not(None),
                Thought.purge_at <= utc_now(),
            )
        )
    )
    for thought in expired:
        permanently_purge_thought(db, thought)
    db.commit()
    return len(expired)
