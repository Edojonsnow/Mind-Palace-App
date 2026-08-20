from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.models import (
    AIProcessingStatus,
    ChatMessage,
    Thought,
    ThoughtChunk,
    User,
)
from app.services.openai_ai import GeneratedAskAnswer


class FakeAskProvider:
    def __init__(self) -> None:
        self.histories: list[list[dict[str, str]]] = []

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def answer_question(
        self,
        question: str,
        context: str,
        history: list[dict[str, str]],
    ) -> GeneratedAskAnswer:
        assert question
        assert "[S1]" in context
        self.histories.append(history)
        return GeneratedAskAnswer(
            answer="Your thought says this is important. [S1]",
            citation_ids=["S1"],
        )


def add_ready_thought(db_session: Session, user: User, body: str) -> Thought:
    thought = Thought(
        user_id=user.id,
        body=body,
        thought_type="thought",
        source_type="manual",
        manual_tags=[],
        storage_scope="cloud",
        use_with_ask_my_mind=True,
        ai_processing_status=AIProcessingStatus.READY.value,
        is_archived=False,
    )
    db_session.add(thought)
    db_session.flush()
    db_session.add(
        ThoughtChunk(
            user_id=user.id,
            thought_id=thought.id,
            chunk_text=body,
            chunk_index=0,
            embedding=[1.0, 0.0, 0.0],
        )
    )
    db_session.commit()
    db_session.refresh(thought)
    return thought


def current_user(db_session: Session) -> User:
    user = db_session.scalar(select(User).where(User.auth_user_id == "test-auth-user"))
    assert user is not None
    return user


def test_ask_retrieves_sources_and_persists_chat_history(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    client.get("/settings")
    thought = add_ready_thought(
        db_session,
        current_user(db_session),
        "I want to protect time for focused work.",
    )
    provider = FakeAskProvider()
    monkeypatch.setattr("app.services.ask.OpenAIProvider", lambda: provider)

    first_response = client.post("/ask", json={"question": "What matters to me?"})

    assert first_response.status_code == 200
    first_body = first_response.json()
    assert first_body["answer"] == "Your thought says this is important. [S1]"
    assert first_body["sources"][0]["thought_id"] == str(thought.id)
    assert first_body["sources"][0]["is_cited"] is True
    conversation_id = first_body["conversation_id"]

    second_response = client.post(
        "/ask",
        json={
            "question": "Can you remind me?",
            "conversation_id": conversation_id,
        },
    )

    assert second_response.status_code == 200
    assert len(provider.histories) == 2
    assert provider.histories[1][0]["role"] == "user"
    assert provider.histories[1][1]["role"] == "assistant"

    history_response = client.get(f"/ask/{conversation_id}")
    assert history_response.status_code == 200
    assert len(history_response.json()["messages"]) == 4
    assert db_session.scalars(select(ChatMessage)).all()


def test_ask_returns_no_source_answer_without_ready_thoughts(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post("/ask", json={"question": "What do I remember?"})

    assert response.status_code == 200
    assert response.json()["sources"] == []
    assert "could not find" in response.json()["answer"]
    assert len(db_session.scalars(select(ChatMessage)).all()) == 2


def test_ask_does_not_persist_history_when_setting_is_disabled(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    client.get("/settings")
    add_ready_thought(db_session, current_user(db_session), "A thought for a private query.")
    settings_response = client.patch("/settings", json={"store_chat_history": False})
    assert settings_response.status_code == 200

    provider = FakeAskProvider()
    monkeypatch.setattr("app.services.ask.OpenAIProvider", lambda: provider)
    response = client.post("/ask", json={"question": "What did I save?"})

    assert response.status_code == 200
    assert response.json()["conversation_id"]
    assert db_session.scalars(select(ChatMessage)).all() == []


def test_retrieval_is_scoped_to_the_current_user(db_session: Session) -> None:
    current = User(auth_user_id="current", email="current@example.com")
    other = User(auth_user_id="other", email="other@example.com")
    db_session.add_all([current, other])
    db_session.flush()
    add_ready_thought(db_session, current, "Current user's thought.")
    add_ready_thought(db_session, other, "Other user's private thought.")

    from app.services.ask import retrieve_relevant_chunks

    results = retrieve_relevant_chunks(db_session, current, [1.0, 0.0, 0.0])

    assert len(results) == 1
    assert results[0].thought.body == "Current user's thought."


def test_pgvector_retrieval_expression_compiles() -> None:
    statement = select(ThoughtChunk.embedding.cosine_distance([0.0] * 1536))

    compiled = str(statement.compile(dialect=postgresql.dialect()))

    assert "<=>" in compiled
