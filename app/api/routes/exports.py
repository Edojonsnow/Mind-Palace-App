from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.api.dependencies import CurrentUser, DbSession
from app.schemas import ExportRequestRead
from app.services.exports import (
    create_export_request,
    get_export_payload,
    get_export_request,
)

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportRequestRead, status_code=status.HTTP_202_ACCEPTED)
def create_export_route(
    db: DbSession,
    user: CurrentUser,
):
    return create_export_request(db, user)


@router.get("/{export_id}", response_model=ExportRequestRead)
def get_export_route(
    export_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    return get_export_request(db, user, export_id)


@router.get("/{export_id}/download")
def download_export_route(
    export_id: UUID,
    db: DbSession,
    user: CurrentUser,
):
    payload = get_export_payload(db, user, export_id)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="mind-palace-export-{export_id}.json"'
        },
    )
