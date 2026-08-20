import logging
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import Settings, settings

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuthenticatedUser:
    auth_user_id: str
    email: str | None = None


def verify_access_token(token: str, app_settings: Settings = settings) -> AuthenticatedUser:
    if not app_settings.neon_auth_jwks_url or not app_settings.neon_auth_issuer:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Auth verification is not configured",
        )

    try:
        jwk_client = PyJWKClient(app_settings.neon_auth_jwks_url)
        signing_key = jwk_client.get_signing_key_from_jwt(token)
        claims = jwt_decode(
            token,
            signing_key.key,
            algorithms=["RS256", "ES256", "EdDSA"],
            audience=app_settings.neon_auth_audience,
            issuer=app_settings.neon_auth_issuer,
            options={"verify_aud": app_settings.neon_auth_audience is not None},
        )
    except (InvalidTokenError, PyJWKClientError) as err:
        token_issuer = None
        if type(err).__name__ == "InvalidIssuerError":
            try:
                unverified_claims = jwt_decode(
                    token,
                    options={
                        "verify_signature": False,
                        "verify_exp": False,
                        "verify_aud": False,
                        "verify_iss": False,
                    },
                )
                token_issuer = unverified_claims.get("iss")
            except InvalidTokenError:
                pass
        logger.warning(
            "Neon Auth token verification failed: %s (token_issuer=%s configured_issuer=%s)",
            type(err).__name__,
            token_issuer,
            app_settings.neon_auth_issuer,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token",
        ) from err

    auth_user_id = claims.get("sub")
    if not auth_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is missing subject",
        )

    return AuthenticatedUser(
        auth_user_id=auth_user_id,
        email=claims.get("email"),
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    return verify_access_token(credentials.credentials)
