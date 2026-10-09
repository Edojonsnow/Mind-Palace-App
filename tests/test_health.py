from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.core.config import settings
from app.main import create_app

client = TestClient(create_app())


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_database_health_requires_token_in_production(monkeypatch) -> None:
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "health_db_check_token", SecretStr("health-secret"))

    assert client.get("/health/db").status_code == 401
    assert client.get(
        "/health/db",
        headers={"X-Health-Check-Token": "wrong-secret"},
    ).status_code == 401


def test_version() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Mind Palace App"
    assert body["version"] == "0.1.0"
