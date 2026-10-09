from sqlalchemy.orm import Session

from app.core.rate_limit import enforce_rate_limit
from app.models import AIPreferences, User
from app.schemas.profile import AIPreferencesUpdate, ProfileUpdate


def update_profile(db: Session, user: User, payload: ProfileUpdate) -> User:
    enforce_rate_limit(user.id, "profile_write")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(user, key, value)
    db.flush()
    return user


def get_ai_preferences(db: Session, user: User) -> AIPreferences | AIPreferencesUpdate:
    return db.get(AIPreferences, user.id) or AIPreferencesUpdate()


def update_ai_preferences(
    db: Session,
    user: User,
    payload: AIPreferencesUpdate,
) -> AIPreferences:
    enforce_rate_limit(user.id, "profile_write")
    preferences = db.get(AIPreferences, user.id)
    if preferences is None:
        preferences = AIPreferences(user_id=user.id)
        db.add(preferences)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(preferences, key, value)
    db.flush()
    return preferences


def allowed_profile_context(db: Session, user: User) -> dict[str, object] | None:
    preferences = db.get(AIPreferences, user.id)
    if preferences is None or not preferences.use_profile_context:
        return None
    return {
        "preferred_name": user.display_name,
        "writing_style": preferences.writing_style,
        "response_detail": preferences.response_detail,
        "personal_goals": preferences.personal_goals,
        "interests": preferences.interests,
    }
