from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserSettings
from app.schemas import UserSettingsUpdate


def get_user_settings(db: Session, user: User) -> UserSettings:
    settings = db.scalar(select(UserSettings).where(UserSettings.user_id == user.id))
    if settings is not None:
        return settings

    settings = UserSettings(user_id=user.id)
    db.add(settings)
    db.flush()
    return settings


def update_user_settings(
    db: Session,
    user: User,
    payload: UserSettingsUpdate,
) -> UserSettings:
    settings = get_user_settings(db, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)

    db.flush()
    return settings
