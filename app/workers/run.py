from threading import Event, Thread

from rq import Worker

from app.core.config import settings
from app.core.queue import get_ai_queue, get_redis_connection
from app.workers.reconcile import run_reconciliation_loop


def main() -> None:
    connection = get_redis_connection()
    worker = Worker([get_ai_queue()], connection=connection)
    stop_event = Event()
    reconciler = Thread(
        target=run_reconciliation_loop,
        args=(stop_event,),
        name="ai-job-reconciler",
        daemon=True,
    )
    reconciler.start()
    try:
        worker.work(with_scheduler=True)
    finally:
        stop_event.set()
        reconciler.join(timeout=settings.ai_reconciliation_interval_seconds)


if __name__ == "__main__":
    main()
