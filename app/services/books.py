from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.models import Book, User
from app.schemas import BookCreate, BookRead


def _normalized(value: str) -> str:
    return " ".join(value.split()).casefold()


def get_book(db: Session, user: User, book_id: UUID) -> Book:
    book = db.scalar(select(Book).where(Book.id == book_id, Book.user_id == user.id))
    if book is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Book not found")
    return book


def get_or_create_book(db: Session, user: User, payload: BookCreate) -> Book:
    title = " ".join(payload.title.split()).strip()
    author = " ".join(payload.author.split()).strip()
    normalized_title = _normalized(title)
    normalized_author = _normalized(author)
    book = db.scalar(
        select(Book).where(
            Book.user_id == user.id,
            Book.normalized_title == normalized_title,
            Book.normalized_author == normalized_author,
        )
    )
    if book is not None:
        return book

    book = Book(
        user_id=user.id,
        title=title,
        author=author,
        normalized_title=normalized_title,
        normalized_author=normalized_author,
    )
    db.add(book)
    db.flush()
    return book


def list_books(db: Session, user: User, query: str | None = None) -> list[BookRead]:
    statement = select(Book).where(Book.user_id == user.id)
    if query and query.strip():
        pattern = f"%{query.strip()}%"
        statement = statement.where(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))
    books = db.scalars(statement.order_by(func.lower(Book.title), func.lower(Book.author))).all()
    return [
        BookRead(
            id=book.id,
            title=book.title,
            author=book.author,
            created_at=book.created_at,
            updated_at=book.updated_at,
            thought_count=sum(thought.deleted_at is None for thought in book.thoughts),
        )
        for book in books
    ]
