from fastapi import APIRouter, Response, status

from app.api.dependencies import CurrentUser, DbSession, RecentAuthentication
from app.core.config import settings
from app.schemas import AccountDeletionRequestRead
from app.schemas.lifecycle import AccountDeletionOptions, PermanentAccountDeletion
from app.services.accounts import (
    cancel_account_deletion,
    create_account_deletion_request,
    get_account_deletion_request,
    permanent_deletion_available,
    permanently_delete_account,
)

router = APIRouter(prefix="/account", tags=["account"])


@router.get("/deletion/options", response_model=AccountDeletionOptions)
def account_deletion_options_route(user: CurrentUser):
    return AccountDeletionOptions(
        recovery_window_days=settings.recovery_window_days,
        permanent_deletion_available=permanent_deletion_available(),
    )


@router.post("/deletion/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_account_route(
    payload: PermanentAccountDeletion,
    db: DbSession,
    user: CurrentUser,
    recent_auth: RecentAuthentication,
):
    permanently_delete_account(db, user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
