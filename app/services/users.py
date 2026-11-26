from hashlib import sha256

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.models import DeletedAuthIdentity, User, UserSettings


def auth_identity_hash(auth_user_id: str) -> str:
    return sha256(auth_user_id.encode("utf-8")).hexdigest()


def reject_deleted_identity(db: Session, auth_user_id: str) -> None:
    if db.get(DeletedAuthIdentity, auth_identity_hash(auth_user_id)) is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="This account has been permanently deleted. Sign up to create a new account.",
        )


def get_or_create_user(db: Session, authenticated_user: AuthenticatedUser) -> User:
    reject_deleted_identity(db, authenticated_user.auth_user_id)
    user = db.scalar(select(User).where(User.auth_user_id == authenticated_user.auth_user_id))
    if user is not None:
        return user

    # Recheck after the lookup in case a concurrent purge removed the user.
    reject_deleted_identity(db, authenticated_user.auth_user_id)
    user = User(
        auth_user_id=authenticated_user.auth_user_id,
        email=authenticated_user.email,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        existing_user = db.scalar(
            select(User).where(User.auth_user_id == authenticated_user.auth_user_id)
        )
        if existing_user is None:
            raise
        return existing_user

    db.add(UserSettings(user_id=user.id))
    db.flush()
    return user
