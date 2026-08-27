from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas import AccountDeletionRequestRead
from app.services.accounts import (
    cancel_account_deletion,
    create_account_deletion_request,
    get_account_deletion_request,
)
from app.services.users import get_or_create_user

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/deletion", response_model=AccountDeletionRequestRead | None)
def get_account_deletion_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return get_account_deletion_request(db, user)


@router.post(
    "/deletion",
    response_model=AccountDeletionRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_account_deletion_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return create_account_deletion_request(db, user)


@router.delete("/deletion", status_code=status.HTTP_204_NO_CONTENT)
def cancel_account_deletion_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    cancel_account_deletion(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
