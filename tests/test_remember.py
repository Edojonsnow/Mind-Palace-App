from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ThoughtMetadata


def test_remember_overview_groups_ai_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    first = client.post(
        "/thoughts",
        json={"body": "A private thought.", "use_with_ask_my_mind": False},
    ).json()
    second = client.post(
        "/thoughts",
        json={"body": "Another private thought.", "use_with_ask_my_mind": False},
    ).json()

    db_session.add_all(
        [
            ThoughtMetadata(
                user_id=UUID(first["user_id"]),
                thought_id=UUID(first["id"]),
                summary="First summary",
                themes=["Focus", "Learning"],
                emotions=["Curiosity"],
                people=[],
                places=[],
                books=["Deep Work"],
                key_questions=[],
                action_items=[],
                deterministic_metadata={},
            ),
            ThoughtMetadata(
                user_id=UUID(second["user_id"]),
                thought_id=UUID(second["id"]),
                summary="Second summary",
                themes=["focus"],
                emotions=["Hope"],
                people=["Maya"],
                places=[],
                books=[],
                key_questions=[],
                action_items=[],
                deterministic_metadata={},
            ),
        ]
    )
    db_session.commit()

    response = client.get("/remember")

    assert response.status_code == 200
    assert response.json() == {
        "thoughts_analyzed": 2,
        "categories": [
            {
                "key": "themes",
                "label": "Themes",
                "items": [
                    {"label": "Focus", "count": 2},
                    {"label": "Learning", "count": 1},
                ],
            },
            {
                "key": "emotions",
                "label": "Emotions",
                "items": [
                    {"label": "Curiosity", "count": 1},
                    {"label": "Hope", "count": 1},
                ],
            },
            {"key": "people", "label": "People", "items": [{"label": "Maya", "count": 1}]},
            {"key": "books", "label": "Books", "items": [{"label": "Deep Work", "count": 1}]},
        ],
    }


def test_remember_overview_excludes_deleted_thoughts(
    client: TestClient,
    db_session: Session,
) -> None:
    thought = client.post("/thoughts", json={"body": "Temporary thought."}).json()
    db_session.add(
        ThoughtMetadata(
            user_id=UUID(thought["user_id"]),
            thought_id=UUID(thought["id"]),
            summary=None,
            themes=["Temporary"],
            emotions=[],
            people=[],
            places=[],
            books=[],
            key_questions=[],
            action_items=[],
            deterministic_metadata={},
        )
    )
    db_session.commit()
    assert client.delete(f"/thoughts/{thought['id']}").status_code == 204

    response = client.get("/remember")

    assert response.status_code == 200
    assert response.json()["thoughts_analyzed"] == 0
    assert all(not category["items"] for category in response.json()["categories"])
