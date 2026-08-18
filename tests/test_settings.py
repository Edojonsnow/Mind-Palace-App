from fastapi.testclient import TestClient


def test_settings_defaults(client: TestClient) -> None:
    response = client.get("/settings")

    assert response.status_code == 200
    body = response.json()
    assert body["default_use_with_ask_my_mind"] is False
    assert body["store_chat_history"] is True
    assert body["mobile_offline_cache_enabled"] is True


def test_update_settings(client: TestClient) -> None:
    response = client.patch(
        "/settings",
        json={
            "default_use_with_ask_my_mind": True,
            "mobile_offline_cache_enabled": False,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["default_use_with_ask_my_mind"] is True
    assert body["store_chat_history"] is True
    assert body["mobile_offline_cache_enabled"] is False


def test_create_thought_uses_user_default(client: TestClient) -> None:
    settings_response = client.patch("/settings", json={"default_use_with_ask_my_mind": True})
    assert settings_response.status_code == 200

    thought_response = client.post("/thoughts", json={"body": "This should use my default."})

    assert thought_response.status_code == 201
    assert thought_response.json()["use_with_ask_my_mind"] is True

