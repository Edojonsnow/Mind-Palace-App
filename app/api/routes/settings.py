from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import UserSettingsRead, UserSettingsUpdate
from app.services.settings import get_user_settings, update_user_settings

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
def get_settings_route(
    db: DbSession,
    user: CurrentUser,
):
    return get_user_settings(db, user)


@router.patch("", response_model=UserSettingsRead)
def update_settings_route(
    payload: UserSettingsUpdate,
    db: DbSession,
    user: CurrentUser,
):
    return update_user_settings(db, user, payload)
