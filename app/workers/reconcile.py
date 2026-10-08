import logging
from threading import Event

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.ai_recovery import reconcile_ai_jobs

logger = logging.getLogger(__name__)


def reconcile_once() -> None:
    with SessionLocal() as db:
        result = reconcile_ai_jobs(db)
    if result.requeued or result.stale_recovered or result.cancelled or result.dispatch_failures:
        logger.info(
            "AI job reconciliation complete: requeued=%s stale_recovered=%s "
            "cancelled=%s dispatch_failures=%s",
            result.requeued,
            result.stale_recovered,
            result.cancelled,
            result.dispatch_failures,
        )


def run_reconciliation_loop(stop_event: Event) -> None:
    while not stop_event.is_set():
        try:
            reconcile_once()
        except Exception:
            logger.exception("AI job reconciliation failed")
        stop_event.wait(settings.ai_reconciliation_interval_seconds)
