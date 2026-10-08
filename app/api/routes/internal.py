import secrets

from fastapi import APIRouter, Header, HTTPException, status

from app.core.config import settings
from app.core.rate_limit import enforce_auth_rate_limit
from app.schemas import AuthRateLimitRequest

router = APIRouter(prefix="/internal", tags=["internal"])


@router.post("/auth-rate-limit", status_code=status.HTTP_204_NO_CONTENT, include_in_schema=False)
def admit_auth_request(
    payload: AuthRateLimitRequest,
    x_internal_auth_rate_limit_token: str | None = Header(default=None),
) -> None:
    configured_token = settings.auth_rate_limit_token
    if not settings.auth_rate_limits_enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication protection is disabled",
        )
    if configured_token is None or not configured_token.get_secret_value():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication protection is not configured",
        )
    if not x_internal_auth_rate_limit_token or not secrets.compare_digest(
        x_internal_auth_rate_limit_token,
        configured_token.get_secret_value(),
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    enforce_auth_rate_limit(payload.client_key, payload.action)
