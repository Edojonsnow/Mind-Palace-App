import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    BackgroundJob,
    BackgroundJobStatus,
    BackgroundJobType,
    ChatConversation,
    ChatMessage,
    ExportRequest,
    ExportRequestStatus,
    Thought,
    ThoughtMetadata,
    User,
    UserSettings,
)
from app.services.data_lifecycle import as_utc, utc_now

logger = logging.getLogger(__name__)


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _thought_payload(thought: Thought) -> dict[str, object]:
    return {
        "id": str(thought.id),
        "title": thought.title,
        "body": thought.body,
        "thought_type": thought.thought_type,
        "source_type": thought.source_type,
        "source_title": thought.source_title,
        "source_author": thought.source_author,
        "source_url": thought.source_url,
        "book_title": thought.book_title,
        "book_author": thought.book_author,
        "page_reference": thought.page_reference,
        "manual_tags": thought.manual_tags,
        "storage_scope": thought.storage_scope,
        "use_with_ask_my_mind": thought.use_with_ask_my_mind,
        "ai_processing_status": thought.ai_processing_status,
        "is_archived": thought.is_archived,
        "created_at": _iso(thought.created_at),
        "updated_at": _iso(thought.updated_at),
        "deleted_at": _iso(thought.deleted_at),
        "purge_at": _iso(thought.purge_at),
    }


def build_export_payload(db: Session, user: User) -> dict[str, object]:
    settings_record = db.scalar(
        select(UserSettings).where(UserSettings.user_id == user.id)
    )
    thoughts = list(
        db.scalars(select(Thought).where(Thought.user_id == user.id).order_by(Thought.created_at))
    )
    metadata = list(
        db.scalars(
            select(ThoughtMetadata)
            .where(ThoughtMetadata.user_id == user.id)
            .order_by(ThoughtMetadata.created_at)
        )
    )
    conversations = list(
        db.scalars(
            select(ChatConversation)
            .where(ChatConversation.user_id == user.id)
            .order_by(ChatConversation.created_at)
        )
    )
    messages = list(
        db.scalars(
            select(ChatMessage)
            .where(ChatMessage.user_id == user.id)
            .order_by(ChatMessage.created_at)
        )
    )

    return {
        "format_version": 1,
        "exported_at": datetime.now(UTC).isoformat(),
        "user": {
            "email": user.email,
            "display_name": user.display_name,
            "created_at": _iso(user.created_at),
        },
        "settings": (
            {
                "default_use_with_ask_my_mind": settings_record.default_use_with_ask_my_mind,
                "store_chat_history": settings_record.store_chat_history,
                "mobile_offline_cache_enabled": settings_record.mobile_offline_cache_enabled,
            }
            if settings_record is not None
            else None
        ),
        "thoughts": [_thought_payload(thought) for thought in thoughts],
        "thought_metadata": [
            {
                "thought_id": str(record.thought_id),
                "summary": record.summary,
                "themes": record.themes,
                "emotions": record.emotions,
                "people": record.people,
                "places": record.places,
                "books": record.books,
                "key_questions": record.key_questions,
                "action_items": record.action_items,
                "created_at": _iso(record.created_at),
                "updated_at": _iso(record.updated_at),
            }
            for record in metadata
        ],
        "chat_conversations": [
            {
                "id": str(conversation.id),
                "created_at": _iso(conversation.created_at),
                "updated_at": _iso(conversation.updated_at),
            }
            for conversation in conversations
        ],
        "chat_messages": [
            {
                "id": str(message.id),
                "conversation_id": str(message.conversation_id),
                "role": message.role,
                "content": message.content,
                "citations": message.citations,
                "created_at": _iso(message.created_at),
            }
            for message in messages
        ],
    }


def create_export_request(db: Session, user: User) -> ExportRequest:
    now = utc_now()
    db.execute(
        delete(ExportRequest).where(
            ExportRequest.user_id == user.id,
            ExportRequest.expires_at <= now,
        )
    )
    export = ExportRequest(
        user_id=user.id,
        status=ExportRequestStatus.PENDING.value,
        expires_at=now + timedelta(hours=settings.export_retention_hours),
    )
    db.add(export)
    db.flush()
    job = BackgroundJob(
        user_id=user.id,
        job_type=BackgroundJobType.GENERATE_EXPORT.value,
        status=BackgroundJobStatus.PENDING.value,
        attempt_count=0,
    )
    db.add(job)
    db.flush()

    db.commit()

    try:
        from app.core.queue import enqueue_export_generation

        enqueue_export_generation(export.id, job.id)
    except Exception as error:
        db.rollback()
        export = db.get(ExportRequest, export.id)
        job = db.get(BackgroundJob, job.id)
        if export is not None:
            export.status = ExportRequestStatus.FAILED.value
            export.error_message = type(error).__name__
        if job is not None:
            job.status = BackgroundJobStatus.FAILED.value
            job.error_message = type(error).__name__
            job.completed_at = datetime.now(UTC)
        db.commit()
        logger.warning("Unable to schedule export: error_type=%s", type(error).__name__)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export service is temporarily unavailable",
        ) from error

    db.refresh(export)
    return export


def process_export(db: Session, export_id: UUID, job_id: UUID) -> None:
    export = db.get(ExportRequest, export_id)
    job = db.get(BackgroundJob, job_id)
    if export is None or job is None:
        return

    user = db.get(User, export.user_id)
    if user is None:
        export.status = ExportRequestStatus.FAILED.value
        export.error_message = "UserNotFound"
        job.status = BackgroundJobStatus.FAILED.value
        job.error_message = "UserNotFound"
        db.commit()
        return

    export.status = ExportRequestStatus.PROCESSING.value
    job.status = BackgroundJobStatus.RUNNING.value
    job.attempt_count += 1
    db.commit()

    try:
        export.payload = build_export_payload(db, user)
        export.status = ExportRequestStatus.COMPLETED.value
        export.completed_at = datetime.now(UTC)
        job.status = BackgroundJobStatus.COMPLETED.value
        job.completed_at = datetime.now(UTC)
        db.commit()
        try:
            from app.core.queue import enqueue_export_expiry

            enqueue_export_expiry(export.id, export.expires_at)
        except Exception as error:
            logger.warning(
                "Unable to schedule export expiry: error_type=%s",
                type(error).__name__,
            )
    except Exception as error:
        db.rollback()
        export = db.get(ExportRequest, export_id)
        job = db.get(BackgroundJob, job_id)
        if export is not None:
            export.status = ExportRequestStatus.FAILED.value
            export.error_message = type(error).__name__
        if job is not None:
            job.status = BackgroundJobStatus.FAILED.value
            job.error_message = type(error).__name__
            job.completed_at = datetime.now(UTC)
        db.commit()
        logger.warning("Export generation failed: error_type=%s", type(error).__name__)


def expire_export_request(db: Session, export_id: UUID) -> None:
    export = db.get(ExportRequest, export_id)
    if export is None or export.status != ExportRequestStatus.COMPLETED.value:
        return
    if as_utc(export.expires_at) > utc_now():
        return
    export.status = ExportRequestStatus.EXPIRED.value
    export.payload = None
    db.commit()


def get_export_request(db: Session, user: User, export_id: UUID) -> ExportRequest:
    export = db.scalar(
        select(ExportRequest).where(
            ExportRequest.id == export_id,
            ExportRequest.user_id == user.id,
        )
    )
    if export is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Export not found")
    return export


def get_export_payload(db: Session, user: User, export_id: UUID) -> dict[str, object]:
    export = get_export_request(db, user, export_id)
    now = datetime.now(UTC)
    if as_utc(export.expires_at) <= now:
        export.status = ExportRequestStatus.EXPIRED.value
        export.payload = None
        db.commit()
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Export has expired")
    if export.status != ExportRequestStatus.COMPLETED.value or export.payload is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Export is not ready",
        )
    return export.payload
