from uuid import UUID

from app.db.session import SessionLocal
from app.services.accounts import process_account_deletion
from app.services.ai_processing import process_ai_job
from app.services.data_lifecycle import process_thought_purge
from app.services.exports import expire_export_request, process_export


def process_thought(job_id: str, thought_id: str) -> None:
    """RQ entry point; all user data access remains scoped through the job row."""
    with SessionLocal() as db:
        process_ai_job(db, UUID(job_id), UUID(thought_id))


def purge_deleted_thought(job_id: str, thought_id: str) -> None:
    """RQ entry point for permanent thought deletion after the recovery window."""
    with SessionLocal() as db:
        process_thought_purge(db, UUID(job_id), UUID(thought_id))


def generate_export(export_id: str, job_id: str) -> None:
    """RQ entry point for asynchronous user data export generation."""
    with SessionLocal() as db:
        process_export(db, UUID(export_id), UUID(job_id))


def expire_export(export_id: str) -> None:
    """RQ entry point for removing an expired export payload."""
    with SessionLocal() as db:
        expire_export_request(db, UUID(export_id))


def purge_deleted_account(request_id: str) -> None:
    """RQ entry point for permanent account data deletion."""
    with SessionLocal() as db:
        process_account_deletion(db, UUID(request_id))
