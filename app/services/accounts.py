import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.rate_limit import enforce_rate_limit
from app.models import (
    AccountDeletionRequest,
    AccountDeletionStatus,
    AIPreferences,
    AIUsageDaily,
    BackgroundJob,
    Book,
    ChatConversation,
    ChatMessage,
    Collection,
    DeletedAuthIdentity,
    ExportRequest,
    IdempotencyRequest,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
    User,
    UserSettings,
)
from app.models.collection import collection_thoughts
from app.services.data_lifecycle import as_utc
from app.services.neon_auth_admin import delete_neon_auth_user
from app.services.users import auth_identity_hash

logger = logging.getLogger(__name__)


def permanent_deletion_available() -> bool:
    return all((settings.neon_api_key, settings.neon_project_id, settings.neon_auth_branch_id))


def lock_account(db: Session, user_id: UUID) -> User | None:
    # Always lock the user before the request, including worker processing.
    return db.scalar(select(User).where(User.id == user_id).with_for_update())


def create_account_deletion_request(db: Session, user: User) -> AccountDeletionRequest:
    if lock_account(db, user.id) is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    existing = db.scalar(
        select(AccountDeletionRequest).where(
            AccountDeletionRequest.user_id == user.id,
            AccountDeletionRequest.status == AccountDeletionStatus.PENDING.value,
        )
    )
    if existing is not None:
        return existing

    enforce_rate_limit(user.id, "account_deletion")
    db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))

    request = AccountDeletionRequest(
        user_id=user.id,
        status=AccountDeletionStatus.PENDING.value,
        purge_at=datetime.now(UTC) + timedelta(days=settings.recovery_window_days),
    )
    db.add(request)
    db.flush()
    db.commit()

    try:
        from app.core.queue import enqueue_account_deletion

        enqueue_account_deletion(request.id, request.purge_at)
    except Exception as error:
        db.rollback()
        request = db.get(AccountDeletionRequest, request.id)
        if request is not None:
            request.error_message = type(error).__name__
            db.commit()
        logger.warning(
            "Unable to schedule account deletion: error_type=%s",
            type(error).__name__,
        )
        # The request is durable; reconciliation can dispatch it after recovery.

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
    if lock_account(db, user.id) is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    request = get_account_deletion_request(db, user)
    if request is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pending account deletion request",
        )
    db.refresh(request)
    if as_utc(request.purge_at) <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Permanent deletion has started and can no longer be cancelled.",
        )
    enforce_rate_limit(user.id, "account_deletion")
    request.status = AccountDeletionStatus.CANCELLED.value
    request.completed_at = datetime.now(UTC)
    db.commit()


def permanently_delete_account(db: Session, user: User) -> None:
    if not permanent_deletion_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Permanent account deletion is not available yet. Contact support.",
        )
    if lock_account(db, user.id) is None:
        raise HTTPException(status_code=401, detail="Account no longer exists")
    enforce_rate_limit(user.id, "account_deletion")
    request = db.scalar(
        select(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id)
    )
    if request is None:
        request = AccountDeletionRequest(user_id=user.id)
        db.add(request)
    request.status = AccountDeletionStatus.PENDING.value
    request.purge_at = datetime.now(UTC)
    request.completed_at = None
    request.error_message = None
    db.flush()
    request_id = request.id
    # Keep an actionable request even if Neon succeeds but the local purge fails.
    db.commit()
    try:
        process_account_deletion(db, request_id)
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Deletion is pending. Please try again or contact support.",
        ) from error


def purge_user_data(db: Session, user: User) -> None:
    identity_hash = auth_identity_hash(user.auth_user_id)
    if db.get(DeletedAuthIdentity, identity_hash) is None:
        db.add(DeletedAuthIdentity(auth_id_hash=identity_hash))
        db.flush()
    db.execute(delete(IdempotencyRequest).where(IdempotencyRequest.user_id == user.id))
    db.execute(delete(AIPreferences).where(AIPreferences.user_id == user.id))
    db.execute(delete(AIUsageDaily).where(AIUsageDaily.user_id == user.id))
    db.execute(delete(ThoughtChunk).where(ThoughtChunk.user_id == user.id))
    db.execute(delete(ThoughtMetadata).where(ThoughtMetadata.user_id == user.id))
    db.execute(delete(ChatMessage).where(ChatMessage.user_id == user.id))
    db.execute(delete(ChatConversation).where(ChatConversation.user_id == user.id))
    db.execute(delete(ExportRequest).where(ExportRequest.user_id == user.id))
    db.execute(delete(BackgroundJob).where(BackgroundJob.user_id == user.id))
    db.execute(delete(AccountDeletionRequest).where(AccountDeletionRequest.user_id == user.id))
    db.execute(delete(UserSettings).where(UserSettings.user_id == user.id))
    db.execute(
        delete(collection_thoughts).where(
            collection_thoughts.c.collection_id.in_(
                select(Collection.id).where(Collection.user_id == user.id)
            )
        )
    )
    db.execute(delete(Thought).where(Thought.user_id == user.id))
    db.execute(delete(Book).where(Book.user_id == user.id))
    db.execute(delete(Collection).where(Collection.user_id == user.id))
    db.delete(user)
    db.commit()


def process_account_deletion(db: Session, request_id: UUID) -> None:
    request = db.get(AccountDeletionRequest, request_id)
    if request is None or request.status != AccountDeletionStatus.PENDING.value:
        return
    user = lock_account(db, request.user_id)
    request = db.scalar(
        select(AccountDeletionRequest)
        .where(AccountDeletionRequest.id == request_id)
        .execution_options(populate_existing=True)
    )
    if request is None or request.status != AccountDeletionStatus.PENDING.value:
        return
    if as_utc(request.purge_at) > datetime.now(UTC):
        return
    if user is None:
        db.delete(request)
        db.commit()
        return

    try:
        delete_neon_auth_user(user.auth_user_id)
        purge_user_data(db, user)
    except Exception as error:
        db.rollback()
        request = db.get(AccountDeletionRequest, request_id)
        if request is not None:
            request.error_message = type(error).__name__
            db.commit()
        logger.warning("Account deletion failed: error_type=%s", type(error).__name__)
        raise


def reconcile_account_deletions(
    db: Session,
    *,
    now: datetime | None = None,
    limit: int | None = None,
) -> tuple[int, int]:
    """Requeue due account purges whose scheduled RQ job was lost."""
    now = now or datetime.now(UTC)
    requests = list(
        db.scalars(
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.status == AccountDeletionStatus.PENDING.value,
                AccountDeletionRequest.purge_at <= now,
            )
            .order_by(AccountDeletionRequest.purge_at.asc(), AccountDeletionRequest.id.asc())
            .limit(limit or settings.account_deletion_reconciliation_batch_size)
        )
    )
    requeued = 0
    failures = 0

    from app.core.queue import enqueue_account_deletion

    for request in requests:
        try:
            enqueue_account_deletion(request.id, now)
        except Exception as error:
            request.error_message = type(error).__name__
            failures += 1
            logger.warning(
                "Unable to requeue account deletion: error_type=%s",
                type(error).__name__,
            )
        else:
            request.error_message = None
            requeued += 1

    if requests:
        db.commit()
    return requeued, failures
