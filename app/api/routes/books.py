from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import BookCreate, BookRead
from app.services.books import get_or_create_book, list_books

router = APIRouter(prefix="/books", tags=["books"])


@router.get("", response_model=list[BookRead])
def list_books_route(
    db: DbSession,
    user: CurrentUser,
    q: Annotated[str | None, Query(max_length=255)] = None,
):
    return list_books(db, user, q)


@router.post("", response_model=BookRead, status_code=status.HTTP_201_CREATED)
def create_book_route(
    payload: BookCreate,
    db: DbSession,
    user: CurrentUser,
):
    book = get_or_create_book(db, user, payload)
    return BookRead(
        id=book.id,
        title=book.title,
        author=book.author,
        created_at=book.created_at,
        updated_at=book.updated_at,
        thought_count=sum(thought.deleted_at is None for thought in book.thoughts),
    )
