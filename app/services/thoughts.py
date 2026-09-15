from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import settings
from app.models import (
    SourceType,
    StorageScope,
    Thought,
    ThoughtMetadata,
    ThoughtType,
    User,
    UserSettings,
)
from app.schemas import ThoughtCreate, ThoughtUpdate, UserSettingsUpdate
from app.services.ai_processing import purge_ai_artifacts, schedule_ai_processing
from app.services.data_lifecycle import schedule_thought_purge

DETERMINISTIC_METADATA_FIELDS = {
    "thought_type",
    "source_type",
    "source_title",
    "source_author",
    "source_url",
    "book_title",
    "book_author",
    "page_reference",
    "manual_tags",
}


def normalize_manual_tags(tags: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        cleaned = " ".join(tag.split()).strip()
        if not cleaned or cleaned.casefold() in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned.casefold())
    return normalized


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
        manual_tags=normalize_manual_tags(payload.manual_tags),
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


@dataclass(frozen=True)
class ThoughtListResult:
    items: list[Thought]
    total: int


def _like_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _metadata_contains(column, value: str):
    return cast(column, Text).ilike(_like_pattern(f'"{value.strip()}"'), escape="\\")


def _thought_filters(
    user: User,
    *,
    query: str | None = None,
    thought_type: ThoughtType | None = None,
    source_type: SourceType | None = None,
    tag: str | None = None,
    book: str | None = None,
    theme: str | None = None,
    emotion: str | None = None,
    person: str | None = None,
    place: str | None = None,
    is_archived: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
):
    filters = [Thought.user_id == user.id, Thought.deleted_at.is_(None)]

    if query and query.strip():
        pattern = _like_pattern(query)
        filters.append(
            or_(
                Thought.title.ilike(pattern, escape="\\"),
                Thought.body.ilike(pattern, escape="\\"),
                Thought.source_title.ilike(pattern, escape="\\"),
                Thought.source_author.ilike(pattern, escape="\\"),
                Thought.book_title.ilike(pattern, escape="\\"),
                Thought.book_author.ilike(pattern, escape="\\"),
            )
        )

    if thought_type is not None:
        filters.append(Thought.thought_type == thought_type.value)
    if source_type is not None:
        filters.append(Thought.source_type == source_type.value)
    if tag and tag.strip():
        tag_json_value = tag.strip().replace("\\", "\\\\").replace('"', '\\"')
        filters.append(
            cast(Thought.manual_tags, Text).ilike(
                _like_pattern(f'"{tag_json_value}"'),
                escape="\\",
            )
        )
    if book and book.strip():
        pattern = _like_pattern(book)
        filters.append(
            or_(
                Thought.book_title.ilike(pattern, escape="\\"),
                Thought.book_author.ilike(pattern, escape="\\"),
                _metadata_contains(ThoughtMetadata.books, book),
            )
        )

    if theme and theme.strip():
        filters.append(_metadata_contains(ThoughtMetadata.themes, theme))
    if emotion and emotion.strip():
        filters.append(_metadata_contains(ThoughtMetadata.emotions, emotion))
    if person and person.strip():
        filters.append(_metadata_contains(ThoughtMetadata.people, person))
    if place and place.strip():
        filters.append(_metadata_contains(ThoughtMetadata.places, place))
    if is_archived is not None:
        filters.append(Thought.is_archived.is_(is_archived))
    if created_from is not None:
        filters.append(Thought.created_at >= created_from)
    if created_to is not None:
        filters.append(Thought.created_at <= created_to)

    return filters


def list_thoughts(
    db: Session,
    user: User,
    *,
    query: str | None = None,
    thought_type: ThoughtType | None = None,
    source_type: SourceType | None = None,
    tag: str | None = None,
    book: str | None = None,
    theme: str | None = None,
    emotion: str | None = None,
    person: str | None = None,
    place: str | None = None,
    is_archived: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: int = 1,
    page_size: int = 20,
) -> ThoughtListResult:
    if created_from is not None and created_to is not None and created_from > created_to:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_from must be before or equal to created_to",
        )

    filters = _thought_filters(
        user,
        query=query,
        thought_type=thought_type,
        source_type=source_type,
        tag=tag,
        book=book,
        theme=theme,
        emotion=emotion,
        person=person,
        place=place,
        is_archived=is_archived,
        created_from=created_from,
        created_to=created_to,
    )
    metadata_join = and_(
        ThoughtMetadata.thought_id == Thought.id,
        ThoughtMetadata.user_id == user.id,
    )
    total = (
        db.scalar(
            select(func.count(func.distinct(Thought.id)))
            .select_from(Thought)
            .outerjoin(ThoughtMetadata, metadata_join)
            .where(*filters)
        )
        or 0
    )
    items = list(
        db.scalars(
            select(Thought)
            .options(selectinload(Thought.metadata_record))
            .outerjoin(ThoughtMetadata, metadata_join)
            .where(*filters)
            .order_by(Thought.created_at.desc(), Thought.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return ThoughtListResult(items=items, total=total)


def get_thought(db: Session, user: User, thought_id: UUID) -> Thought:
    thought = db.scalar(
        select(Thought)
        .options(selectinload(Thought.metadata_record))
        .where(
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
        elif key == "manual_tags" and value is not None:
            value = normalize_manual_tags(value)
        setattr(thought, key, value)

    db.commit()
    db.refresh(thought)

    if not thought.use_with_ask_my_mind and was_ai_enabled:
        purge_ai_artifacts(db, thought)
    elif thought.use_with_ask_my_mind and (
        not was_ai_enabled
        or bool(DETERMINISTIC_METADATA_FIELDS.intersection(values))
        or "body" in values
        or thought.ai_processing_status == "failed"
    ):
        purge_ai_artifacts(db, thought)
        schedule_ai_processing(db, thought)
        db.refresh(thought)
    return thought


def retry_ai_processing(db: Session, user: User, thought_id: UUID) -> Thought:
    thought = get_thought(db, user, thought_id)
    if not thought.use_with_ask_my_mind:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Enable Use with Ask My Mind before retrying organization",
        )

    purge_ai_artifacts(db, thought)
    schedule_ai_processing(db, thought)
    db.refresh(thought)
    return thought


def soft_delete_thought(db: Session, user: User, thought_id: UUID) -> None:
    thought = get_thought(db, user, thought_id)
    deleted_at = datetime.now(UTC)
    thought.deleted_at = deleted_at
    thought.purge_at = deleted_at + timedelta(days=settings.recovery_window_days)
    db.commit()
    db.refresh(thought)
    schedule_thought_purge(db, thought)


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
