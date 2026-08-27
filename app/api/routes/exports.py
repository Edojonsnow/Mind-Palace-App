from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.schemas import ExportRequestRead
from app.services.exports import (
    create_export_request,
    get_export_payload,
    get_export_request,
)
from app.services.users import get_or_create_user

router = APIRouter(prefix="/exports", tags=["exports"])


@router.post("", response_model=ExportRequestRead, status_code=status.HTTP_202_ACCEPTED)
def create_export_route(
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return create_export_request(db, user)


@router.get("/{export_id}", response_model=ExportRequestRead)
def get_export_route(
    export_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    return get_export_request(db, user, export_id)


@router.get("/{export_id}/download")
def download_export_route(
    export_id: UUID,
    db: Annotated[Session, Depends(get_db)],
    authenticated_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
):
    user = get_or_create_user(db, authenticated_user)
    payload = get_export_payload(db, user, export_id)
    return JSONResponse(
        content=payload,
        headers={
            "Content-Disposition": f'attachment; filename="mind-palace-export-{export_id}.json"'
        },
    )
