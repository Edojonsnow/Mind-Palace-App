from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import ThoughtMetadata


def create_thought(client: TestClient, **overrides: object) -> dict:
    payload = {"body": "A useful thought for recall."}
    payload.update(overrides)
    response = client.post("/thoughts", json=payload)
    assert response.status_code == 201
    return response.json()


def test_recall_searches_text_and_returns_pagination_headers(client: TestClient) -> None:
    create_thought(
        client,
        title="Deep work",
        body="Protect focused work each morning.",
        manual_tags=["focus"],
    )
    create_thought(client, title="Reading list", body="Book notes for later.")

    response = client.get(
        "/thoughts",
        params={"q": "FOCUSED", "page_size": 10},
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert [thought["title"] for thought in response.json()] == ["Deep work"]
    assert response.headers["X-Total-Count"] == "1"
    assert response.headers["X-Page"] == "1"
    assert response.headers["X-Page-Size"] == "10"
    assert response.headers["X-Total-Pages"] == "1"
    assert "X-Total-Count" in response.headers["Access-Control-Expose-Headers"]


def test_recall_composes_metadata_filters(client: TestClient) -> None:
    create_thought(
        client,
        title="Atomic Habits quote",
        body="Small actions compound over time.",
        thought_type="quote",
        source_type="book",
        book_title="Atomic Habits",
        book_author="James Clear",
        manual_tags=["reading", "habits"],
        is_archived=True,
    )
    create_thought(
        client,
        title="Habit reflection",
        body="Make the next action smaller.",
        thought_type="journal",
        source_type="manual",
        manual_tags=["habits"],
    )

    response = client.get(
        "/thoughts",
        params={
            "thought_type": "quote",
            "source_type": "book",
            "tag": "reading",
            "book": "atomic",
            "is_archived": "true",
        },
    )

    assert response.status_code == 200
    thoughts = response.json()
    assert len(thoughts) == 1
    assert thoughts[0]["title"] == "Atomic Habits quote"


def test_recall_filters_by_generated_theme_and_emotion(
    client: TestClient,
    db_session: Session,
) -> None:
    first = create_thought(
        client,
        title="Focus reflection",
        body="A reflection.",
        use_with_ask_my_mind=False,
    )
    second = create_thought(
        client,
        title="Rest reflection",
        body="Another reflection.",
        use_with_ask_my_mind=False,
    )
    db_session.add_all(
        [
            ThoughtMetadata(
                user_id=UUID(first["user_id"]),
                thought_id=UUID(first["id"]),
                summary=None,
                themes=["Focus"],
                emotions=["Calm"],
                people=[],
                places=[],
                books=[],
                key_questions=[],
                action_items=[],
                deterministic_metadata={},
            ),
            ThoughtMetadata(
                user_id=UUID(second["user_id"]),
                thought_id=UUID(second["id"]),
                summary=None,
                themes=["Rest"],
                emotions=["Hope"],
                people=[],
                places=[],
                books=[],
                key_questions=[],
                action_items=[],
                deterministic_metadata={},
            ),
        ]
    )
    db_session.commit()

    theme_response = client.get("/thoughts", params={"theme": "focus"})
    emotion_response = client.get("/thoughts", params={"emotion": "hope"})
    combined_response = client.get(
        "/thoughts",
        params={"theme": "focus", "emotion": "calm"},
    )

    assert [thought["title"] for thought in theme_response.json()] == ["Focus reflection"]
    assert [thought["title"] for thought in emotion_response.json()] == ["Rest reflection"]
    assert [thought["title"] for thought in combined_response.json()] == ["Focus reflection"]


def test_recall_book_filter_includes_ai_detected_books(
    client: TestClient,
    db_session: Session,
) -> None:
    thought = create_thought(
        client,
        title="Reading reflection",
        body="A note about a book.",
        use_with_ask_my_mind=False,
    )
    db_session.add(
        ThoughtMetadata(
            user_id=UUID(thought["user_id"]),
            thought_id=UUID(thought["id"]),
            summary=None,
            themes=[],
            emotions=[],
            people=[],
            places=[],
            books=["Deep Work"],
            key_questions=[],
            action_items=[],
            deterministic_metadata={},
        )
    )
    db_session.commit()

    response = client.get("/thoughts", params={"book": "deep work"})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Reading reflection"]


def test_recall_filters_by_saved_book_id(client: TestClient) -> None:
    first_book = client.post(
        "/books",
        json={"title": "Circe", "author": "Madeline Miller"},
    ).json()
    second_book = client.post(
        "/books",
        json={"title": "Piranesi", "author": "Susanna Clarke"},
    ).json()
    create_thought(
        client,
        title="Circe excerpt",
        body="A saved excerpt from Circe.",
        thought_type="book_excerpt",
        book_id=first_book["id"],
    )
    create_thought(
        client,
        title="Piranesi excerpt",
        body="A saved excerpt from Piranesi.",
        thought_type="book_excerpt",
        book_id=second_book["id"],
    )

    response = client.get("/thoughts", params={"book_id": first_book["id"]})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()] == ["Circe excerpt"]


def test_recall_paginates_deterministically(client: TestClient) -> None:
    created = [create_thought(client, title=f"Thought {index}") for index in range(3)]

    first_page = client.get("/thoughts", params={"page": 1, "page_size": 2})
    repeated_first_page = client.get("/thoughts", params={"page": 1, "page_size": 2})
    second_page = client.get("/thoughts", params={"page": 2, "page_size": 2})

    assert first_page.status_code == 200
    assert repeated_first_page.status_code == 200
    assert second_page.status_code == 200
    first_page_ids = [thought["id"] for thought in first_page.json()]
    repeated_first_page_ids = [thought["id"] for thought in repeated_first_page.json()]
    second_page_ids = [thought["id"] for thought in second_page.json()]
    assert first_page_ids == repeated_first_page_ids
    assert len(first_page_ids) == 2
    assert len(second_page_ids) == 1
    assert set(first_page_ids + second_page_ids) == {thought["id"] for thought in created}
    assert second_page.headers["X-Total-Count"] == "3"
    assert second_page.headers["X-Total-Pages"] == "2"


def test_recall_rejects_an_invalid_date_range(client: TestClient) -> None:
    response = client.get(
        "/thoughts",
        params={
            "created_from": "2026-08-21T00:00:00Z",
            "created_to": "2026-08-20T00:00:00Z",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "created_from must be before or equal to created_to"
