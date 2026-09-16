from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import BackgroundJob, User
from app.services.ai_processing import process_ai_job
from app.services.openai_ai import ExtractedThoughtMetadata, GeneratedAskAnswer


class FakeOrganizationProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0, 0.0] for _ in texts]

    def extract_metadata(self, thought_body: str) -> ExtractedThoughtMetadata:
        return ExtractedThoughtMetadata(
            summary="A focused work thought.",
            themes=["career development"],
            emotions=["happy"],
            people=["Alex"],
            key_questions=["What should I protect?"],
        )


class FakeAskProvider:
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
        return GeneratedAskAnswer(
            answer="Protect focused work. [S1]",
            citation_ids=["S1"],
        )


def no_op_enqueue(*args: object, **kwargs: object) -> None:
    return None


def current_user(db_session: Session) -> User:
    user = db_session.scalar(select(User).where(User.auth_user_id == "test-auth-user"))
    assert user is not None
    return user


def test_mvp_workflow_covers_capture_organization_recall_ask_and_restore(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    client.get("/settings")
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)

    create_response = client.post(
        "/thoughts",
        json={
            "title": "Protect focused work",
            "body": "I should protect time for focused work and thoughtful decisions.",
            "use_with_ask_my_mind": True,
        },
    )

    assert create_response.status_code == 201
    created = create_response.json()
    assert created["ai_processing_status"] == "pending"
    thought_id = UUID(created["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    process_ai_job(
        db_session,
        job.id,
        thought_id,
        provider_factory=FakeOrganizationProvider,
    )

    recall_response = client.get("/thoughts", params={"theme": "Work"})
    assert recall_response.status_code == 200
    recalled = recall_response.json()
    assert len(recalled) == 1
    assert recalled[0]["id"] == str(thought_id)
    assert recalled[0]["ai_metadata"]["themes"] == ["Work"]
    assert recalled[0]["ai_metadata"]["emotions"] == ["Joy"]

    remember_response = client.get("/remember")
    assert remember_response.status_code == 200
    assert remember_response.json()["thoughts_analyzed"] == 1

    monkeypatch.setattr("app.services.ask.OpenAIProvider", FakeAskProvider)
    ask_response = client.post("/ask", json={"question": "What should I protect?"})
    assert ask_response.status_code == 200
    assert ask_response.json()["answer"] == "Protect focused work. [S1]"
    assert ask_response.json()["sources"][0]["thought_id"] == str(thought_id)
    assert ask_response.json()["sources"][0]["is_cited"] is True

    delete_response = client.delete(f"/thoughts/{thought_id}")
    assert delete_response.status_code == 204
    assert client.get("/thoughts", params={"theme": "Work"}).json() == []
    assert client.get("/remember").json()["thoughts_analyzed"] == 0

    restore_response = client.post(f"/thoughts/{thought_id}/restore")
    assert restore_response.status_code == 200
    assert restore_response.json()["deleted_at"] is None
    assert len(client.get("/thoughts", params={"theme": "Work"}).json()) == 1
    assert client.post("/ask", json={"question": "What should I protect?"}).json()["sources"]
