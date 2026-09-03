from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import Thought, ThoughtMetadata, User
from tests.conftest import OTHER_USER_ID


def no_op_enqueue(*args: object, **kwargs: object) -> None:
    return None


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
    assert body["ai_metadata"] is None


def test_thought_response_includes_generated_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    thought = client.post("/thoughts", json={"body": "A thought about focused work."}).json()
    db_session.add(
        ThoughtMetadata(
            user_id=UUID(thought["user_id"]),
            thought_id=UUID(thought["id"]),
            summary="A focused work reflection.",
            themes=["Focus"],
            emotions=["Calm"],
            people=[],
            places=[],
            books=[],
            key_questions=["How can I protect focus?"],
            action_items=["Block focused work time."],
            deterministic_metadata={"thought_type": "thought"},
        )
    )
    db_session.commit()

    response = client.get(f"/thoughts/{thought['id']}")

    assert response.status_code == 200
    assert response.json()["ai_metadata"] == {
        "summary": "A focused work reflection.",
        "themes": ["Focus"],
        "emotions": ["Calm"],
        "people": [],
        "places": [],
        "books": [],
        "key_questions": ["How can I protect focus?"],
        "action_items": ["Block focused work time."],
        "deterministic_metadata": {"thought_type": "thought"},
        "created_at": response.json()["ai_metadata"]["created_at"],
        "updated_at": response.json()["ai_metadata"]["updated_at"],
    }


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


def test_organize_retries_ai_processing_for_enabled_thought(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    thought = client.post(
        "/thoughts",
        json={"body": "Retry this organization.", "use_with_ask_my_mind": True},
    ).json()

    response = client.post(f"/thoughts/{thought['id']}/organize")

    assert response.status_code == 200
    assert response.json()["ai_processing_status"] == "pending"
    assert response.json()["ai_metadata"] is None
    assert db_session.query(ThoughtMetadata).count() == 0


def test_organize_rejects_ai_disabled_thought(client: TestClient) -> None:
    thought = client.post("/thoughts", json={"body": "No organization yet."}).json()

    response = client.post(f"/thoughts/{thought['id']}/organize")

    assert response.status_code == 400
    assert response.json()["detail"] == "Enable Use with Ask My Mind before retrying organization"


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
