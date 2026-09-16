from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser
from app.models import User, UserSettings


def get_or_create_user(db: Session, authenticated_user: AuthenticatedUser) -> User:
    user = db.scalar(select(User).where(User.auth_user_id == authenticated_user.auth_user_id))
    if user is not None:
        return user

    user = User(
        auth_user_id=authenticated_user.auth_user_id,
        email=authenticated_user.email,
    )
    db.add(user)
    db.flush()

    db.add(UserSettings(user_id=user.id))
    db.flush()
    return user
