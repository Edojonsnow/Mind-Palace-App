from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from jwt.exceptions import InvalidTokenError, PyJWKClientError
from sqlalchemy.orm import Session

from app.core.auth import verify_access_token
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
