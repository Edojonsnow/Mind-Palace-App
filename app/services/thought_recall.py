from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import Text, and_, cast, func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.models import SourceType, Thought, ThoughtMetadata, ThoughtType, User


@dataclass(frozen=True)
class ThoughtListResult:
    items: list[Thought]
    total: int


@dataclass(frozen=True)
class RecallQuery:
    """Product-level query for deterministic thought recall."""

    query: str | None = None
    thought_type: ThoughtType | None = None
    source_type: SourceType | None = None
    book_id: UUID | None = None
    tag: str | None = None
    book: str | None = None
    theme: str | None = None
    emotion: str | None = None
    person: str | None = None
    place: str | None = None
    is_archived: bool | None = None
    created_from: datetime | None = None
    created_to: datetime | None = None
    page: int = 1
    page_size: int = 20


def _like_pattern(value: str) -> str:
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _metadata_contains(column, value: str):
    return cast(column, Text).ilike(_like_pattern(f'"{value.strip()}"'), escape="\\")


def _thought_filters(user: User, recall_query: RecallQuery):
    filters = [Thought.user_id == user.id, Thought.deleted_at.is_(None)]

    if recall_query.query and recall_query.query.strip():
        pattern = _like_pattern(recall_query.query)
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

    if recall_query.thought_type is not None:
        filters.append(Thought.thought_type == recall_query.thought_type.value)
    if recall_query.source_type is not None:
        filters.append(Thought.source_type == recall_query.source_type.value)
    if recall_query.book_id is not None:
        filters.append(Thought.book_id == recall_query.book_id)
    if recall_query.tag and recall_query.tag.strip():
        tag_json_value = recall_query.tag.strip().replace("\\", "\\\\").replace('"', '\\"')
        filters.append(
            cast(Thought.manual_tags, Text).ilike(
                _like_pattern(f'"{tag_json_value}"'),
                escape="\\",
            )
        )
    if recall_query.book and recall_query.book.strip():
        pattern = _like_pattern(recall_query.book)
        filters.append(
            or_(
                Thought.book_title.ilike(pattern, escape="\\"),
                Thought.book_author.ilike(pattern, escape="\\"),
                _metadata_contains(ThoughtMetadata.books, recall_query.book),
            )
        )

    if recall_query.theme and recall_query.theme.strip():
        filters.append(_metadata_contains(ThoughtMetadata.themes, recall_query.theme))
    if recall_query.emotion and recall_query.emotion.strip():
        filters.append(_metadata_contains(ThoughtMetadata.emotions, recall_query.emotion))
    if recall_query.person and recall_query.person.strip():
        filters.append(_metadata_contains(ThoughtMetadata.people, recall_query.person))
    if recall_query.place and recall_query.place.strip():
        filters.append(_metadata_contains(ThoughtMetadata.places, recall_query.place))
    if recall_query.is_archived is not None:
        filters.append(Thought.is_archived.is_(recall_query.is_archived))
    if recall_query.created_from is not None:
        filters.append(Thought.created_at >= recall_query.created_from)
    if recall_query.created_to is not None:
        filters.append(Thought.created_at <= recall_query.created_to)

    return filters


def list_thoughts(db: Session, user: User, recall_query: RecallQuery) -> ThoughtListResult:
    if (
        recall_query.created_from is not None
        and recall_query.created_to is not None
        and recall_query.created_from > recall_query.created_to
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="created_from must be before or equal to created_to",
        )

    filters = _thought_filters(user, recall_query)
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
            .offset((recall_query.page - 1) * recall_query.page_size)
            .limit(recall_query.page_size)
        )
    )
    return ThoughtListResult(items=items, total=total)
