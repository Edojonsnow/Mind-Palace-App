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
