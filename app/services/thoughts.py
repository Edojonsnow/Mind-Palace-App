from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StorageScope, Thought, User, UserSettings
from app.schemas import ThoughtCreate, ThoughtUpdate, UserSettingsUpdate
from app.services.ai_processing import purge_ai_artifacts, schedule_ai_processing


def create_thought(db: Session, user: User, payload: ThoughtCreate) -> Thought:
    if payload.storage_scope is StorageScope.LOCAL_DEVICE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Local-device thoughts are not accepted by the backend",
        )

    settings = get_user_settings(db, user)
    use_with_ask = (
        settings.default_use_with_ask_my_mind
        if payload.use_with_ask_my_mind is None
        else payload.use_with_ask_my_mind
    )
    thought = Thought(
        user_id=user.id,
        title=payload.title,
        body=payload.body,
        thought_type=payload.thought_type.value,
        source_type=payload.source_type.value,
        source_title=payload.source_title,
        source_author=payload.source_author,
        source_url=str(payload.source_url) if payload.source_url else None,
        book_title=payload.book_title,
        book_author=payload.book_author,
        page_reference=payload.page_reference,
        manual_tags=payload.manual_tags,
        storage_scope=payload.storage_scope.value,
        use_with_ask_my_mind=use_with_ask,
        is_archived=payload.is_archived,
    )
    db.add(thought)
    db.commit()
    db.refresh(thought)
    if thought.use_with_ask_my_mind:
        schedule_ai_processing(db, thought)
        db.refresh(thought)
    return thought


def list_thoughts(db: Session, user: User) -> list[Thought]:
    return list(
        db.scalars(
            select(Thought)
            .where(Thought.user_id == user.id, Thought.deleted_at.is_(None))
            .order_by(Thought.created_at.desc())
        )
    )


def get_thought(db: Session, user: User, thought_id: UUID) -> Thought:
    thought = db.scalar(
        select(Thought).where(
            Thought.id == thought_id,
            Thought.user_id == user.id,
            Thought.deleted_at.is_(None),
        )
    )
    if thought is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thought not found")
    return thought


def update_thought(db: Session, user: User, thought_id: UUID, payload: ThoughtUpdate) -> Thought:
    thought = get_thought(db, user, thought_id)
    was_ai_enabled = thought.use_with_ask_my_mind
    values = payload.model_dump(exclude_unset=True)
    for key, value in values.items():
        if key in {"thought_type", "source_type"} and value is not None:
            value = value.value
        elif key == "source_url" and value is not None:
            value = str(value)
        setattr(thought, key, value)

    db.commit()
    db.refresh(thought)

    if not thought.use_with_ask_my_mind and was_ai_enabled:
        purge_ai_artifacts(db, thought)
    elif thought.use_with_ask_my_mind and (
        not was_ai_enabled or "body" in values or thought.ai_processing_status == "failed"
    ):
        schedule_ai_processing(db, thought)
        db.refresh(thought)
    return thought


def soft_delete_thought(db: Session, user: User, thought_id: UUID) -> None:
    thought = get_thought(db, user, thought_id)
    thought.deleted_at = datetime.now(UTC)
    db.commit()


def get_user_settings(db: Session, user: User) -> UserSettings:
    settings = db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    if settings is not None:
        return settings

    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.commit()
    db.refresh(settings)
    return settings


def update_user_settings(
    db: Session,
    user: User,
    payload: UserSettingsUpdate,
) -> UserSettings:
    settings = get_user_settings(db, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)

    db.commit()
    db.refresh(settings)
    return settings
