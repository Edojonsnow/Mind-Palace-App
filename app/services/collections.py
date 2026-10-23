from datetime import UTC, datetime
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import and_, delete, desc, func, insert, select
from sqlalchemy.orm import Session, selectinload

from app.core.rate_limit import enforce_rate_limit
from app.models import Collection, Thought, User
from app.models.collection import collection_thoughts
from app.schemas import CollectionCreate, CollectionRead, CollectionUpdate, ThoughtRead


def _normalize_name(value: str) -> tuple[str, str]:
    name = " ".join(value.split()).strip()
    return name, name.casefold()


def _collection_statement(user: User):
    return (
        select(Collection, func.count(Thought.id).label("thought_count"))
        .outerjoin(
            collection_thoughts,
            collection_thoughts.c.collection_id == Collection.id,
        )
        .outerjoin(
            Thought,
            and_(
                Thought.id == collection_thoughts.c.thought_id,
                Thought.deleted_at.is_(None),
            ),
        )
        .where(Collection.user_id == user.id)
        .group_by(
            Collection.id,
            Collection.name,
            Collection.normalized_name,
            Collection.last_accessed_at,
            Collection.created_at,
            Collection.updated_at,
        )
    )


def _to_read(collection: Collection, thought_count: int) -> CollectionRead:
    return CollectionRead(
        id=collection.id,
        name=collection.name,
        thought_count=thought_count,
        last_accessed_at=collection.last_accessed_at,
        created_at=collection.created_at,
        updated_at=collection.updated_at,
    )


def get_collection(
    db: Session,
    user: User,
    collection_id: UUID,
    *,
    mark_accessed: bool = False,
) -> CollectionRead:
    result = db.execute(
        _collection_statement(user).where(Collection.id == collection_id)
    ).one_or_none()
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")

    collection, thought_count = result
    if mark_accessed:
        collection.last_accessed_at = datetime.now(UTC)
        db.commit()
        db.refresh(collection)
    return _to_read(collection, thought_count)


def get_collection_record(db: Session, user: User, collection_id: UUID) -> Collection:
    collection = db.scalar(
        select(Collection).where(
            Collection.id == collection_id,
            Collection.user_id == user.id,
        )
    )
    if collection is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


def list_collections(
    db: Session,
    user: User,
    *,
    recent: bool = False,
    limit: int = 100,
    query: str | None = None,
) -> list[CollectionRead]:
    statement = _collection_statement(user)
    if query and query.strip():
        statement = statement.where(Collection.name.ilike(f"%{query.strip()}%"))

    if recent:
        statement = statement.order_by(
            desc(func.coalesce(Collection.last_accessed_at, Collection.created_at)),
            desc(Collection.created_at),
            desc(Collection.id),
        )
    else:
        statement = statement.order_by(func.lower(Collection.name), Collection.id)

    return [
        _to_read(collection, thought_count)
        for collection, thought_count in db.execute(statement.limit(limit)).all()
    ]


def create_collection(db: Session, user: User, payload: CollectionCreate) -> CollectionRead:
    enforce_rate_limit(user.id, "collection_write")
    name, normalized_name = _normalize_name(payload.name)
    existing = db.scalar(
        select(Collection).where(
            Collection.user_id == user.id,
            Collection.normalized_name == normalized_name,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection with this name already exists",
        )

    collection = Collection(
        user_id=user.id,
        name=name,
        normalized_name=normalized_name,
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _to_read(collection, 0)


def update_collection(
    db: Session,
    user: User,
    collection_id: UUID,
    payload: CollectionUpdate,
) -> CollectionRead:
    enforce_rate_limit(user.id, "collection_write")
    collection = get_collection_record(db, user, collection_id)
    name, normalized_name = _normalize_name(payload.name)
    existing = db.scalar(
        select(Collection).where(
            Collection.user_id == user.id,
            Collection.normalized_name == normalized_name,
            Collection.id != collection.id,
        )
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A collection with this name already exists",
        )

    collection.name = name
    collection.normalized_name = normalized_name
    db.commit()
    return get_collection(db, user, collection.id)


def delete_collection(db: Session, user: User, collection_id: UUID) -> None:
    enforce_rate_limit(user.id, "collection_write")
    collection = get_collection_record(db, user, collection_id)
    db.execute(
        delete(collection_thoughts).where(collection_thoughts.c.collection_id == collection.id)
    )
    db.delete(collection)
    db.commit()


def add_thought_to_collection(
    db: Session,
    user: User,
    collection_id: UUID,
    thought_id: UUID,
) -> CollectionRead:
    enforce_rate_limit(user.id, "collection_write")
    collection = get_collection_record(db, user, collection_id)
    thought = db.scalar(
        select(Thought).where(
            Thought.id == thought_id,
            Thought.user_id == user.id,
            Thought.deleted_at.is_(None),
        )
    )
    if thought is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Thought not found")

    existing = db.execute(
        select(collection_thoughts).where(
            collection_thoughts.c.collection_id == collection.id,
            collection_thoughts.c.thought_id == thought.id,
        )
    ).first()
    if existing is None:
        db.execute(
            insert(collection_thoughts).values(
                collection_id=collection.id,
                thought_id=thought.id,
            )
        )
    collection.last_accessed_at = datetime.now(UTC)
    db.commit()
    return get_collection(db, user, collection.id)


def remove_thought_from_collection(
    db: Session,
    user: User,
    collection_id: UUID,
    thought_id: UUID,
) -> None:
    enforce_rate_limit(user.id, "collection_write")
    collection = get_collection_record(db, user, collection_id)
    db.execute(
        delete(collection_thoughts).where(
            collection_thoughts.c.collection_id == collection.id,
            collection_thoughts.c.thought_id == thought_id,
        )
    )
    collection.last_accessed_at = datetime.now(UTC)
    db.commit()


def list_collection_thoughts(
    db: Session,
    user: User,
    collection_id: UUID,
) -> list[ThoughtRead]:
    collection = get_collection_record(db, user, collection_id)
    collection.last_accessed_at = datetime.now(UTC)
    db.commit()
    thoughts = db.scalars(
        select(Thought)
        .options(selectinload(Thought.metadata_record))
        .join(
            collection_thoughts,
            collection_thoughts.c.thought_id == Thought.id,
        )
        .where(
            collection_thoughts.c.collection_id == collection.id,
            Thought.user_id == user.id,
            Thought.deleted_at.is_(None),
        )
        .order_by(Thought.created_at.desc(), Thought.id.desc())
    ).all()
    return [ThoughtRead.model_validate(thought) for thought in thoughts]
