from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.profile import (
    AIPreferencesRead,
    AIPreferencesUpdate,
    ProfileRead,
    ProfileUpdate,
)
from app.services.profile import get_ai_preferences, update_ai_preferences, update_profile

router = APIRouter(prefix="/profile", tags=["profile"])


@router.get("", response_model=ProfileRead)
def get_profile_route(user: CurrentUser):
    return user


@router.patch("", response_model=ProfileRead)
def update_profile_route(payload: ProfileUpdate, db: DbSession, user: CurrentUser):
    return update_profile(db, user, payload)


@router.get("/ai-preferences", response_model=AIPreferencesRead)
def get_ai_preferences_route(db: DbSession, user: CurrentUser):
    return get_ai_preferences(db, user)


@router.patch("/ai-preferences", response_model=AIPreferencesRead)
def update_ai_preferences_route(
    payload: AIPreferencesUpdate,
    db: DbSession,
    user: CurrentUser,
):
    return update_ai_preferences(db, user, payload)
