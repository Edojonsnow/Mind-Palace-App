from uuid import UUID

from app.db.session import SessionLocal
from app.services.ai_processing import process_ai_job


def process_thought(job_id: str, thought_id: str) -> None:
    """RQ entry point; all user data access remains scoped through the job row."""
    with SessionLocal() as db:
        process_ai_job(db, UUID(job_id), UUID(thought_id))
