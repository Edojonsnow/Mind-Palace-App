import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.queue import enqueue_ai_processing
from app.models import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    Thought,
)
from app.services.ai_processing import purge_ai_artifacts
from app.services.ai_processing_content import enrichment_source_hash

logger = logging.getLogger(__name__)


@dataclass
class AIJobReconciliationResult:
    requeued: int = 0
    stale_recovered: int = 0
    cancelled: int = 0
    dispatch_failures: int = 0


def reconcile_ai_jobs(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> AIJobReconciliationResult:
    """Repair durable AI jobs whose Redis dispatch was lost or whose worker died.

    Postgres remains the source of truth. Row locks prevent multiple worker
    reconcilers from dispatching the same database job concurrently, while RQ's
    unique enqueue closes the crash window between Redis persistence steps.
    """
    now = now or datetime.now(UTC)
    stale_before = now - timedelta(seconds=settings.ai_job_stale_after_seconds)
    batch_size = limit or settings.ai_reconciliation_batch_size
    eligible = select(BackgroundJob).where(
        BackgroundJob.job_type == BackgroundJobType.CHUNK_THOUGHT.value,
        or_(
            and_(
                BackgroundJob.status == BackgroundJobStatus.PENDING.value,
                or_(
                    BackgroundJob.not_before.is_(None),
                    BackgroundJob.not_before <= now,
                ),
            ),
            and_(
                BackgroundJob.status == BackgroundJobStatus.RUNNING.value,
                or_(
                    BackgroundJob.started_at.is_(None),
                    BackgroundJob.started_at <= stale_before,
                ),
            ),
        ),
    ).order_by(BackgroundJob.created_at.asc(), BackgroundJob.id.asc()).limit(batch_size)
    jobs = db.scalars(eligible.with_for_update(skip_locked=True)).all()
    result = AIJobReconciliationResult()

    for job in jobs:
        thought = db.get(Thought, job.thought_id) if job.thought_id is not None else None
        if thought is None:
            _cancel_job(db, job, now)
            result.cancelled += 1
            continue

        if thought.deleted_at is not None or not thought.use_with_ask_my_mind:
            purge_ai_artifacts(db, thought, commit=False)
            _cancel_job(db, job, now)
            result.cancelled += 1
            continue

        source_hash = job.source_hash or enrichment_source_hash(thought)
        if enrichment_source_hash(thought) != source_hash:
            _cancel_job(db, job, now)
            result.cancelled += 1
            continue

        if job.status == BackgroundJobStatus.RUNNING.value:
            logger.warning("Reclaiming stale AI job: job_id=%s", job.id)
            job.status = BackgroundJobStatus.PENDING.value
            job.started_at = None
            job.completed_at = None
            result.stale_recovered += 1

        try:
            enqueue_ai_processing(job.id, thought.id)
        except Exception as error:
            job.status = BackgroundJobStatus.PENDING.value
            job.started_at = None
            job.not_before = now + timedelta(seconds=settings.ai_queue_retry_delay_seconds)
            job.error_message = type(error).__name__
            db.commit()
            result.dispatch_failures += 1
            logger.warning(
                "Unable to requeue AI job: job_id=%s error_type=%s",
                job.id,
                type(error).__name__,
            )
            continue

        job.status = BackgroundJobStatus.PENDING.value
        job.started_at = None
        job.not_before = None
        job.error_message = None
        db.commit()
        result.requeued += 1

    return result


def _cancel_job(db: Session, job: BackgroundJob, now: datetime) -> None:
    job.status = BackgroundJobStatus.CANCELLED.value
    job.started_at = None
    job.not_before = None
    job.completed_at = now
    job.error_message = None
    db.commit()
