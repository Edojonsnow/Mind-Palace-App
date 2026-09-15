from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas import BookCreate, BookRead
from app.services.books import get_or_create_book, list_books
from app.services.users import get_or_create_user

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=list[BookRead])
def list_books_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    q: Annotated[str | None, Query(max_length=255)] = None,
):
    user = get_or_create_user(db, authenticated_user)
    return list_books(db, user, q)


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book_route(
    payload: BookCreate,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    book = get_or_create_book(db, user, payload)
    return BookRead(
        id=book.id,
        title=book.title,
        author=book.author,
        created_at=book.created_at,
        updated_at=book.updated_at,
        thought_count=sum(thought.deleted_at is None for thought in book.thoughts),
    )
