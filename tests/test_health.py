from fastapi.testclient import TestClient

from app.main import create_app


client = TestClient(create_app())


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version() -> None:
    response = client.get("/version")

    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Mind Palace App"
    assert body["version"] == "0.1.0"

