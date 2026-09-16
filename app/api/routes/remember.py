from fastapi import APIRouter

from app.api.dependencies import CurrentUser, DbSession
from app.schemas.remember import RememberOverview
from app.services.remember import get_remember_overview

router = APIRouter(prefix="/remember", tags=["remember"])


@router.get("", response_model=RememberOverview)
def get_remember_overview_route(
    db: DbSession,
    user: CurrentUser,
):
    return get_remember_overview(db, user)
