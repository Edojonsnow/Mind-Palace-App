import logging
from dataclasses import dataclass
from typing import Annotated
from urllib.parse import unquote

import httpx
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWKClient
from jwt import decode as jwt_decode
from jwt.exceptions import InvalidTokenError, PyJWKClientError

from app.core.config import Settings, settings

bearer_scheme = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

NEON_AUTH_SESSION_COOKIE = "__Secure-neon-auth.session_token"
NEON_AUTH_SESSION_COOKIE_HEADER = "X-Neon-Auth-Session-Cookie"


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


async def verify_session_token(
    token: str,
    app_settings: Settings = settings,
    *,
    signed_cookie: bool = False,
) -> AuthenticatedUser | None:
    """Validate a Neon Auth session token through the managed session endpoint.

    Neon Auth may return an opaque session token when its JWT response header is
    unavailable. Opaque tokens cannot be verified locally, so validate them by
    sending the same session cookie to Neon Auth's get-session endpoint.
    """

    base_url = app_settings.neon_auth_base_url
    if not base_url and app_settings.neon_auth_jwks_url:
        jwks_suffix = "/.well-known/jwks.json"
        if app_settings.neon_auth_jwks_url.endswith(jwks_suffix):
            base_url = app_settings.neon_auth_jwks_url[: -len(jwks_suffix)]
    base_url = base_url or app_settings.neon_auth_issuer
    if not base_url:
        return None

    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.get(
                f"{base_url.rstrip('/')}/get-session",
                headers={
                    (
                        "Cookie"
                        if signed_cookie or token.count(".") == 1
                        else "Authorization"
                    ): (
                        f"{NEON_AUTH_SESSION_COOKIE}={unquote(token)}"
                        if signed_cookie or token.count(".") == 1
                        else f"Bearer {token}"
                    ),
                    "Origin": app_settings.cors_origins[0]
                    if app_settings.cors_origins
                    else "http://localhost:3000",
                    "x-neon-auth-middleware": "true",
                },
            )
    except httpx.HTTPError as err:
        logger.warning("Neon Auth session validation request failed: %s", type(err).__name__)
        return None

    if response.status_code != httpx.codes.OK:
        return None

    try:
        payload = response.json()
    except ValueError:
        return None

    if not isinstance(payload, dict):
        return None

    session = payload.get("session")
    user = payload.get("user")
    if not isinstance(session, dict) or not isinstance(user, dict):
        return None

    auth_user_id = user.get("id") or session.get("userId")
    if not isinstance(auth_user_id, str) or not auth_user_id:
        return None

    email = user.get("email")
    return AuthenticatedUser(
        auth_user_id=auth_user_id,
        email=email if isinstance(email, str) else None,
    )


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session_cookie: Annotated[str | None, Header(alias=NEON_AUTH_SESSION_COOKIE_HEADER)] = None,
) -> AuthenticatedUser:
    if session_cookie:
        session_user = await verify_session_token(session_cookie, signed_cookie=True)
        if session_user is not None:
            return session_user

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )

    token = credentials.credentials
    if token.count(".") != 2:
        session_user = await verify_session_token(token)
        if session_user is not None:
            return session_user

    try:
        return verify_access_token(token)
    except HTTPException as token_error:
        if token_error.status_code != status.HTTP_401_UNAUTHORIZED:
            raise

        session_user = await verify_session_token(token)
        if session_user is not None:
            return session_user
        raise
