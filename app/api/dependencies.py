"""Shared dependencies for authenticated API routes."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.services.users import get_or_create_user

DbSession = Annotated[Session, Depends(get_db)]
CurrentAuthUser = Annotated[AuthenticatedUser, Depends(get_current_user)]


def get_current_app_user(db: DbSession, authenticated_user: CurrentAuthUser) -> User:
    return get_or_create_user(db, authenticated_user)


CurrentUser = Annotated[User, Depends(get_current_app_user)]


def require_recent_authentication(authenticated_user: CurrentAuthUser) -> None:
    created_at = authenticated_user.session_created_at
    age = (
        (datetime.now(UTC) - created_at).total_seconds()
        if created_at is not None and created_at.tzinfo is not None
        else None
    )
    # A refreshed JWT is not proof of a recent sign-in; use the provider session.
    if age is None or age < -30 or age > settings.account_deletion_recent_auth_seconds:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sign out and sign in again before permanently deleting your account.",
        )


RecentAuthentication = Annotated[None, Depends(require_recent_authentication)]
IdempotencyKey = Annotated[
    str | None,
    Header(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9_-]+$"),
]
