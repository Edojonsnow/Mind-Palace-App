from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import AIUsageRead, OnboardingUpdate, UserSettingsRead, UserSettingsUpdate
from app.services.ai_usage import get_ai_usage
from app.services.settings import get_user_settings, update_onboarding, update_user_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
def get_settings_route(
    db: DbSession,
    user: CurrentUser,
):
    return get_user_settings(db, user)


@router.get("/ai-usage", response_model=AIUsageRead)
def get_ai_usage_route(db: DbSession, user: CurrentUser):
    return get_ai_usage(db, user)


@router.patch("", response_model=UserSettingsRead)
def update_settings_route(
    payload: UserSettingsUpdate,
    db: DbSession,
    user: CurrentUser,
):
    return update_user_settings(db, user, payload)


@router.patch("/onboarding", response_model=UserSettingsRead)
def update_onboarding_route(
    payload: OnboardingUpdate,
    db: DbSession,
    user: CurrentUser,
):
    return update_onboarding(db, user, payload)
