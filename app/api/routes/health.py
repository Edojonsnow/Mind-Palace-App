import secrets
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, status
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.config import settings
from app.db.session import engine

router = APIRouter(tags=["system"])


@router.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def database_health_check(
    health_check_token: Annotated[str | None, Header(alias="X-Health-Check-Token")] = None,
) -> dict[str, str]:
    configured_token = settings.health_db_check_token
    requires_token = settings.app_env.strip().lower() in {"staging", "production"}
    if requires_token or configured_token is not None:
        if configured_token is None or not configured_token.get_secret_value():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Database health check is not configured",
            )
        if not health_check_token or not secrets.compare_digest(
            health_check_token,
            configured_token.get_secret_value(),
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except SQLAlchemyError as err:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database unavailable",
        ) from err

    return {"status": "ok"}


@router.get("/version")
def version() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "version": settings.app_version,
    }
