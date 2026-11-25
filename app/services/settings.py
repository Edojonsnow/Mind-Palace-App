from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.rate_limit import enforce_rate_limit
from app.models import User, UserSettings
from app.schemas import OnboardingUpdate, UserSettingsUpdate


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
    enforce_rate_limit(user.id, "settings_write")
    settings = get_user_settings(db, user)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(settings, key, value)

    db.flush()
    return settings


def complete_onboarding(db: Session, user_id: UUID) -> None:
    # The first saved thought and its onboarding completion commit together.
    db.execute(
        update(UserSettings)
        .where(
            UserSettings.user_id == user_id,
            UserSettings.onboarding_completed_at.is_(None),
        )
        .values(onboarding_completed_at=datetime.now(UTC))
    )


def update_onboarding(db: Session, user: User, payload: OnboardingUpdate) -> UserSettings:
    enforce_rate_limit(user.id, "settings_write")
    settings = get_user_settings(db, user)
    if payload.action == "skip":
        complete_onboarding(db, user.id)
    else:
        db.execute(
            update(UserSettings)
            .where(
                UserSettings.user_id == user.id,
                UserSettings.onboarding_completed_at.is_(None),
            )
            .values(onboarding_step="first_thought")
        )
    db.flush()
    db.refresh(settings)
    return settings
