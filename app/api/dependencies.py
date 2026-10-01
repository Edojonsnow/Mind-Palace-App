"""Shared dependencies for authenticated API routes."""

from typing import Annotated

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models import User
from app.services.users import get_or_create_user

DbSession = Annotated[Session, Depends(get_db)]
CurrentAuthUser = Annotated[AuthenticatedUser, Depends(get_current_user)]
def get_current_app_user(db: DbSession, authenticated_user: CurrentAuthUser) -> User:
    return get_or_create_user(db, authenticated_user)


CurrentUser = Annotated[User, Depends(get_current_app_user)]
IdempotencyKey = Annotated[
    str | None,
    Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
]
