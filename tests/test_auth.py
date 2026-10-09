from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from pydantic import SecretStr
from sqlalchemy.orm import Session

from app.core.auth import (
    AuthenticatedUser,
    get_current_user,
    verify_access_token,
    verify_session_token,
)
from app.core.config import Settings
from app.db.session import get_db
from app.main import create_app


def test_protected_routes_require_bearer_token(db_session: Session) -> None:
    app = create_app()

    def override_get_db() -> Session:
        return db_session

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as client:
        response = client.get("/settings")

    app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "Authentication required"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_staging_and_production_require_auth_audience(app_env: str) -> None:
    with pytest.raises(ValueError, match="Production security configuration is missing"):
        Settings(app_env=app_env, neon_auth_audience=" ")


@pytest.mark.parametrize("missing_setting", ["health", "internal"])
def test_production_requires_operational_endpoint_protection(missing_setting: str) -> None:
    values = {
        "app_env": "production",
        "neon_auth_audience": "mind-palace",
        "health_db_check_token": SecretStr("health-secret"),
        "auth_rate_limits_enabled": True,
        "auth_rate_limit_token": SecretStr("auth-secret"),
    }
    if missing_setting == "health":
        values["health_db_check_token"] = SecretStr(" ")
    else:
        values["auth_rate_limits_enabled"] = False

    with pytest.raises(ValueError, match="Production security configuration is missing"):
        Settings(**values)


def test_local_auth_audience_can_remain_disabled() -> None:
    app_settings = Settings(app_env="local", neon_auth_audience=" ")

    assert app_settings.neon_auth_audience is None


def test_verify_access_token_requires_auth_configuration() -> None:
    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(
            "token",
            SimpleNamespace(
                neon_auth_jwks_url=None,
                neon_auth_issuer=None,
                neon_auth_audience=None,
            ),
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail == "Auth verification is not configured"


def test_verify_access_token_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeJWKClient:
        def __init__(self, jwks_url: str) -> None:
            self.jwks_url = jwks_url

        def get_signing_key_from_jwt(self, token: str) -> object:
            raise PyJWKClientError("bad key")

    monkeypatch.setattr("app.core.auth.PyJWKClient", FakeJWKClient)

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(
            "bad-token",
            SimpleNamespace(
                neon_auth_jwks_url="https://auth.example.com/.well-known/jwks.json",
                neon_auth_issuer="https://auth.example.com",
                neon_auth_audience=None,
            ),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid authentication token"


def test_verify_access_token_returns_authenticated_user(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeJWKClient:
        def __init__(self, jwks_url: str) -> None:
            self.jwks_url = jwks_url

        def get_signing_key_from_jwt(self, token: str) -> object:
            return SimpleNamespace(key="fake-public-key")

    def fake_decode(
        token: str,
        key: str,
        algorithms: list[str],
        audience: str | None,
        issuer: str,
        options: dict[str, bool],
    ) -> dict[str, str]:
        assert token == "valid-token"
        assert key == "fake-public-key"
        assert algorithms == ["RS256", "ES256", "EdDSA"]
        assert audience == "mind-palace"
        assert issuer == "https://auth.example.com"
        assert options == {"verify_aud": True}
        return {"sub": "neon-user-123", "email": "alex@example.com"}

    monkeypatch.setattr("app.core.auth.PyJWKClient", FakeJWKClient)
    monkeypatch.setattr("app.core.auth.jwt_decode", fake_decode)

    user = verify_access_token(
        "valid-token",
        SimpleNamespace(
            neon_auth_jwks_url="https://auth.example.com/.well-known/jwks.json",
            neon_auth_issuer="https://auth.example.com",
            neon_auth_audience="mind-palace",
        ),
    )

    assert user.auth_user_id == "neon-user-123"
    assert user.email == "alex@example.com"


def test_verify_access_token_requires_subject(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeJWKClient:
        def __init__(self, jwks_url: str) -> None:
            self.jwks_url = jwks_url

        def get_signing_key_from_jwt(self, token: str) -> object:
            return SimpleNamespace(key="fake-public-key")

    def fake_decode(*args: object, **kwargs: object) -> dict[str, str]:
        return {"email": "alex@example.com"}

    monkeypatch.setattr("app.core.auth.PyJWKClient", FakeJWKClient)
    monkeypatch.setattr("app.core.auth.jwt_decode", fake_decode)

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(
            "token-without-sub",
            SimpleNamespace(
                neon_auth_jwks_url="https://auth.example.com/.well-known/jwks.json",
                neon_auth_issuer="https://auth.example.com",
                neon_auth_audience=None,
            ),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Authentication token is missing subject"


def test_verify_access_token_maps_decode_errors_to_unauthorized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeJWKClient:
        def __init__(self, jwks_url: str) -> None:
            self.jwks_url = jwks_url

        def get_signing_key_from_jwt(self, token: str) -> object:
            return SimpleNamespace(key="fake-public-key")

    def fake_decode(*args: object, **kwargs: object) -> dict[str, str]:
        raise InvalidTokenError("bad token")

    monkeypatch.setattr("app.core.auth.PyJWKClient", FakeJWKClient)
    monkeypatch.setattr("app.core.auth.jwt_decode", fake_decode)

    with pytest.raises(HTTPException) as exc_info:
        verify_access_token(
            "bad-token",
            SimpleNamespace(
                neon_auth_jwks_url="https://auth.example.com/.well-known/jwks.json",
                neon_auth_issuer="https://auth.example.com",
                neon_auth_audience=None,
            ),
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail == "Invalid authentication token"


@pytest.mark.asyncio
async def test_get_current_user_accepts_opaque_neon_session_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify_session_token(
        token: str,
        app_settings: object = object(),
    ) -> AuthenticatedUser:
        assert token == "opaque-session-token"
        return AuthenticatedUser(auth_user_id="neon-user-123", email="alex@example.com")

    monkeypatch.setattr("app.core.auth.verify_session_token", fake_verify_session_token)

    user = await get_current_user(
        SimpleNamespace(credentials="opaque-session-token"),
    )

    assert user.auth_user_id == "neon-user-123"
    assert user.email == "alex@example.com"


@pytest.mark.asyncio
async def test_get_current_user_accepts_signed_session_cookie_from_web_proxy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_verify_session_token(
        token: str,
        app_settings: object = object(),
        *,
        signed_cookie: bool = False,
    ) -> AuthenticatedUser:
        assert token == "session-token.signature"
        assert signed_cookie is True
        return AuthenticatedUser(auth_user_id="neon-user-123")

    monkeypatch.setattr("app.core.auth.verify_session_token", fake_verify_session_token)

    user = await get_current_user(
        SimpleNamespace(credentials=None),
        "session-token.signature",
    )

    assert user.auth_user_id == "neon-user-123"


@pytest.mark.asyncio
async def test_verify_session_token_returns_user_from_neon_session_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResponse:
        status_code = 200

        def json(self) -> dict[str, object]:
            return {
                "session": {"userId": "neon-user-123"},
                "user": {"id": "neon-user-123", "email": "alex@example.com"},
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            assert timeout == 3.0

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, *args: object) -> None:
            return None

        async def get(self, url: str, *, headers: dict[str, str]) -> FakeResponse:
            assert url == "https://auth.example.com/neondb/auth/get-session"
            assert headers == {
                "Cookie": "__Secure-neon-auth.session_token=opaque-session-token",
                "Origin": "http://localhost:3000",
                "x-neon-auth-middleware": "true",
            }
            return FakeResponse()

    monkeypatch.setattr("app.core.auth.httpx.AsyncClient", FakeAsyncClient)

    user = await verify_session_token(
        "opaque-session-token",
            SimpleNamespace(
                neon_auth_base_url=None,
                neon_auth_jwks_url="https://auth.example.com/neondb/auth/.well-known/jwks.json",
                neon_auth_issuer="https://auth.example.com",
                backend_cors_origins="http://localhost:3000",
                cors_origins=["http://localhost:3000"],
            ),
    )

    assert user == AuthenticatedUser(auth_user_id="neon-user-123", email="alex@example.com")
