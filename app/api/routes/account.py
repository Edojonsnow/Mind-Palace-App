from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import AccountDeletionRequestRead
from app.services.accounts import (
    cancel_account_deletion,
    create_account_deletion_request,
    get_account_deletion_request,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/deletion", response_model=AccountDeletionRequestRead | None)
def get_account_deletion_route(
    db: DbSession,
    user: CurrentUser,
):
    return get_account_deletion_request(db, user)


@router.post(
    "/deletion",
    response_model=AccountDeletionRequestRead,
    status_code=status.HTTP_202_ACCEPTED,
)
def request_account_deletion_route(
    db: DbSession,
    user: CurrentUser,
):
    return create_account_deletion_request(db, user)


@router.delete("/deletion", status_code=status.HTTP_204_NO_CONTENT)
def cancel_account_deletion_route(
    db: DbSession,
    user: CurrentUser,
):
    cancel_account_deletion(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
