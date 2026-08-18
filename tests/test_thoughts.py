from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Thought, User
from tests.conftest import OTHER_USER_ID


def test_create_thought_defaults_ai_participation_off(client: TestClient) -> None:
    response = client.post(
        "/thoughts",
        json={
            "body": "I want Mind Palace to keep capture simple.",
            "thought_type": "thought",
            "manual_tags": ["product"],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["body"] == "I want Mind Palace to keep capture simple."
    assert body["storage_scope"] == "cloud"
    assert body["use_with_ask_my_mind"] is False
    assert body["manual_tags"] == ["product"]


def test_create_thought_rejects_local_device_storage(client: TestClient) -> None:
    response = client.post(
        "/thoughts",
        json={
            "body": "Keep this only on my phone.",
            "storage_scope": "local_device",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Local-device thoughts are not accepted by the backend"


def test_list_thoughts_is_scoped_to_current_user(client: TestClient, db_session: Session) -> None:
    other_user = User(
        id=OTHER_USER_ID,
        auth_user_id="other-auth-user",
        email="other@example.com",
    )
    db_session.add(other_user)
    db_session.add(
        Thought(
            user_id=other_user.id,
            body="This belongs to someone else.",
            thought_type="thought",
            source_type="manual",
            manual_tags=[],
            storage_scope="cloud",
            use_with_ask_my_mind=False,
            is_archived=False,
        )
    )
    db_session.commit()

    response = client.post("/thoughts", json={"body": "This belongs to the active user."})
    assert response.status_code == 201

    list_response = client.get("/thoughts")

    assert list_response.status_code == 200
    thoughts = list_response.json()
    assert len(thoughts) == 1
    assert thoughts[0]["body"] == "This belongs to the active user."


def test_update_thought_can_enable_ask_my_mind(client: TestClient) -> None:
    create_response = client.post("/thoughts", json={"body": "A thought about discipline."})
    thought_id = create_response.json()["id"]

    response = client.patch(
        f"/thoughts/{thought_id}",
        json={"use_with_ask_my_mind": True, "manual_tags": ["discipline"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["use_with_ask_my_mind"] is True
    assert body["manual_tags"] == ["discipline"]


def test_soft_deleted_thought_is_hidden(client: TestClient) -> None:
    create_response = client.post("/thoughts", json={"body": "Delete this later."})
    thought_id = create_response.json()["id"]

    delete_response = client.delete(f"/thoughts/{thought_id}")
    assert delete_response.status_code == 204

    get_response = client.get(f"/thoughts/{thought_id}")
    assert get_response.status_code == 404

    list_response = client.get("/thoughts")
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_get_other_users_thought_returns_404(client: TestClient, db_session: Session) -> None:
    other_user = User(
        id=OTHER_USER_ID,
        auth_user_id="other-auth-user",
        email="other@example.com",
    )
    db_session.add(other_user)
    thought = Thought(
        user_id=other_user.id,
        body="Private thought from another user.",
        thought_type="thought",
        source_type="manual",
        manual_tags=[],
        storage_scope="cloud",
        use_with_ask_my_mind=False,
        is_archived=False,
    )
    db_session.add(thought)
    db_session.commit()
    db_session.refresh(thought)

    response = client.get(f"/thoughts/{UUID(str(thought.id))}")

    assert response.status_code == 404

