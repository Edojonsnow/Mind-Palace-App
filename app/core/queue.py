from datetime import datetime
from uuid import UUID

from redis import Redis
from rq import Queue

from app.core.config import settings


def get_redis_connection() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
    )


def get_ai_queue() -> Queue:
    return Queue(settings.ai_queue_name, connection=get_redis_connection())


def enqueue_ai_processing(job_id: UUID, thought_id: UUID) -> None:
    from app.workers.tasks import process_thought

    get_ai_queue().enqueue(
        process_thought,
        str(job_id),
        str(thought_id),
        job_id=str(job_id),
        result_ttl=0,
    )


def enqueue_thought_purge(job_id: UUID, thought_id: UUID, run_at: datetime | None) -> None:
    from app.workers.tasks import purge_deleted_thought

    if run_at is None:
        raise ValueError("Thought purge requires a scheduled time")
    get_ai_queue().enqueue_at(
        run_at,
        purge_deleted_thought,
        str(job_id),
        str(thought_id),
        job_id=f"purge-thought-{job_id}",
        result_ttl=0,
    )


def enqueue_export_generation(export_id: UUID, job_id: UUID) -> None:
    from app.workers.tasks import generate_export

    get_ai_queue().enqueue(
        generate_export,
        str(export_id),
        str(job_id),
        job_id=f"generate-export-{export_id}",
        result_ttl=0,
    )


def enqueue_export_expiry(export_id: UUID, run_at: datetime) -> None:
    from app.workers.tasks import expire_export

    get_ai_queue().enqueue_at(
        run_at,
        expire_export,
        str(export_id),
        job_id=f"expire-export-{export_id}",
        result_ttl=0,
    )


def enqueue_account_deletion(request_id: UUID, run_at: datetime) -> None:
    from app.workers.tasks import purge_deleted_account

    get_ai_queue().enqueue_at(
        run_at,
        purge_deleted_account,
        str(request_id),
        job_id=f"purge-account-{request_id}",
        result_ttl=0,
    )
