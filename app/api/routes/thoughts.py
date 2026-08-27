import logging
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models import SourceType, ThoughtType
from app.schemas import ThoughtCreate, ThoughtRead, ThoughtUpdate
from app.services.data_lifecycle import list_deleted_thoughts, restore_thought
from app.services.thoughts import (
    create_thought,
    get_thought,
    list_thoughts,
    soft_delete_thought,
    update_thought,
)
from app.services.users import get_or_create_user

router = APIRouter(prefix="/thoughts", tags=["thoughts"])
logger = logging.getLogger(__name__)


@router.post("", response_model=ThoughtRead, status_code=status.HTTP_201_CREATED)
def create_thought_route(
    payload: ThoughtCreate,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return create_thought(db, user, payload)


@router.get("", response_model=list[ThoughtRead])
def list_thoughts_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    response: Response,
    q: Annotated[str | None, Query(max_length=200)] = None,
    thought_type: ThoughtType | None = None,
    source_type: SourceType | None = None,
    tag: Annotated[str | None, Query(max_length=100)] = None,
    book: Annotated[str | None, Query(max_length=255)] = None,
    is_archived: bool | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    logger.info(
        "Recall request received: has_query=%s query_length=%d has_tag=%s has_book=%s "
        "thought_type=%s source_type=%s is_archived=%s page=%d page_size=%d",
        bool(q and q.strip()),
        len(q.strip()) if q else 0,
        bool(tag and tag.strip()),
        bool(book and book.strip()),
        thought_type.value if thought_type else None,
        source_type.value if source_type else None,
        is_archived,
        page,
        page_size,
    )
    user = get_or_create_user(db, authenticated_user)
    result = list_thoughts(
        db,
        user,
        query=q,
        thought_type=thought_type,
        source_type=source_type,
        tag=tag,
        book=book,
        is_archived=is_archived,
        created_from=created_from,
        created_to=created_to,
        page=page,
        page_size=page_size,
    )
    response.headers["X-Total-Count"] = str(result.total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str((result.total + page_size - 1) // page_size)
    logger.info(
        "Recall response returned: total_matches=%d returned_count=%d page=%d page_size=%d",
        result.total,
        len(result.items),
        page,
        page_size,
    )
    return result.items


@router.get("/deleted", response_model=list[ThoughtRead])
def list_deleted_thoughts_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return list_deleted_thoughts(db, user)


@router.get("/{thought_id}", response_model=ThoughtRead)
def get_thought_route(
    thought_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return get_thought(db, user, thought_id)


@router.patch("/{thought_id}", response_model=ThoughtRead)
def update_thought_route(
    thought_id: UUID,
    payload: ThoughtUpdate,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return update_thought(db, user, thought_id, payload)


@router.delete("/{thought_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_thought_route(
    thought_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    soft_delete_thought(db, user, thought_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{thought_id}/restore", response_model=ThoughtRead)
def restore_thought_route(
    thought_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return restore_thought(db, user, thought_id)
