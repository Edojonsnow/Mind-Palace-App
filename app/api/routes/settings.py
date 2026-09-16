from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas import UserSettingsRead, UserSettingsUpdate
from app.services.settings import get_user_settings, update_user_settings
from app.services.users import get_or_create_user

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
def get_settings_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return get_user_settings(db, user)


@router.patch("", response_model=UserSettingsRead)
def update_settings_route(
    payload: UserSettingsUpdate,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return update_user_settings(db, user, payload)
