import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AccountDeletionRequest,
    AccountDeletionStatus,
    BackgroundJob,
    ChatConversation,
    ChatMessage,
    ExportRequest,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
    User,
    UserSettings,
)
from app.services.data_lifecycle import as_utc

logger = logging.getLogger(__name__)


def create_account_deletion_request(db: Session, user: User) -> AccountDeletionRequest:
    existing = db.scalar(
        select(AccountDeletionRequest).where(
            AccountDeletionRequest.user_id == user.id,
            AccountDeletionRequest.status == AccountDeletionStatus.PENDING.value,
        )
    )
    if existing is not None:
        return existing

    db.execute(
        delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id)
    )

    request = AccountDeletionRequest(
        user_id=user.id,
        status=AccountDeletionStatus.PENDING.value,
        purge_at=datetime.now(UTC) + timedelta(days=settings.recovery_window_days),
    )
    db.add(request)
    db.flush()
    try:
        from app.core.queue import enqueue_account_deletion

        enqueue_account_deletion(request.id, request.purge_at)
    except Exception as error:
        db.rollback()
        logger.warning(
            "Unable to schedule account deletion: error_type=%s",
            type(error).__name__,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Account deletion service is temporarily unavailable",
        ) from error

    db.commit()
    db.refresh(request)
    return request


def get_account_deletion_request(
    db: Session,
    user: User,
) -> AccountDeletionRequest | None:
    return db.scalar(
        select(AccountDeletionRequest).where(
            AccountDeletionRequest.user_id == user.id,
            AccountDeletionRequest.status == AccountDeletionStatus.PENDING.value,
        )
    )


def cancel_account_deletion(db: Session, user: User) -> None:
    request = get_account_deletion_request(db, user)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account deletion request",
        )
    request.status = AccountDeletionStatus.CANCELLED.value
    request.completed_at = datetime.now(UTC)
    db.commit()


def purge_user_data(db: Session, user: User) -> None:
    db.execute(delete(ThoughtChunk).where(ThoughtChunk.user_id == user.id))
    db.execute(delete(ThoughtMetadata).where(ThoughtMetadata.user_id == user.id))
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.execute(delete(ChatConversation).where(ChatConversation.user_id == user.id))
    db.execute(delete(ExportRequest).where(ExportRequest.user_id == user.id))
    db.execute(delete(BackgroundJob).where(BackgroundJob.user_id == user.id))
    db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))
    db.execute(delete(UserSettings).where(UserSettings.user_id == user.id))
    db.execute(delete(Thought).where(Thought.user_id == user.id))
    db.delete(user)
    db.commit()


def process_account_deletion(db: Session, request_id: UUID) -> None:
    request = db.get(AccountDeletionRequest, request_id)
    if request is None or request.status != AccountDeletionStatus.PENDING.value:
        return
    if as_utc(request.purge_at) > datetime.now(UTC):
        return

    user = db.get(User, request.user_id)
    if user is None:
        db.delete(request)
        db.commit()
        return

    try:
        purge_user_data(db, user)
    except Exception as error:
        db.rollback()
        request = db.get(AccountDeletionRequest, request_id)
        if request is not None:
            request.error_message = type(error).__name__
            db.commit()
        logger.warning("Account deletion failed: error_type=%s", type(error).__name__)
