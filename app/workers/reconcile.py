import logging
from threading import Event

from app.core.config import settings
from app.db.session import SessionLocal
from app.services.accounts import reconcile_account_deletions
from app.services.ai_recovery import reconcile_ai_jobs
from app.services.data_lifecycle import purge_expired_thoughts

logger = logging.getLogger(__name__)


def reconcile_once() -> None:
    with SessionLocal() as db:
        result = reconcile_ai_jobs(db)
        account_requeued, account_failures = reconcile_account_deletions(db)
        expired_thoughts = purge_expired_thoughts(db)
    if (
        result.requeued
        or result.stale_recovered
        or result.cancelled
        or result.dispatch_failures
        or account_requeued
        or account_failures
        or expired_thoughts
    ):
        logger.info(
            "Worker reconciliation complete: requeued=%s stale_recovered=%s "
            "cancelled=%s dispatch_failures=%s account_requeued=%s "
            "account_failures=%s expired_thoughts=%s",
            result.requeued,
            result.stale_recovered,
            result.cancelled,
            result.dispatch_failures,
            account_requeued,
            account_failures,
            expired_thoughts,
        )


def run_reconciliation_loop(stop_event: Event) -> None:
    while not stop_event.is_set():
        try:
            reconcile_once()
        except Exception:
            logger.exception("AI job reconciliation failed")
        stop_event.wait(settings.ai_reconciliation_interval_seconds)
