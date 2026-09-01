from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas.remember import RememberOverview
from app.services.remember import get_remember_overview
from app.services.users import get_or_create_user

router = APIRouter(prefix="/remember", tags=["remember"])


@router.get("", response_model=RememberOverview)
def get_remember_overview_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return get_remember_overview(db, user)
