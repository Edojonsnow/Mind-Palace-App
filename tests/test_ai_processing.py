from types import SimpleNamespace
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    AIProcessingStatus,
    BackgroundJob,
    BackgroundJobStatus,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
)
from app.services.ai_processing import process_ai_job
from app.services.openai_ai import ExtractedThoughtMetadata, OpenAIProvider


class FakeAIProvider:
    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[float(index), 1.0, 2.0] for index, _ in enumerate(texts)]

    def extract_metadata(self, thought_body: str) -> ExtractedThoughtMetadata:
        return ExtractedThoughtMetadata(
            summary="A focused test thought.",
            themes=["testing"],
            key_questions=["Does the pipeline preserve privacy?"],
        )


def no_op_enqueue(*args: object, **kwargs: object) -> None:
    return None


def test_openai_provider_adapts_embeddings_and_structured_metadata() -> None:
    class FakeEmbeddings:
        def create(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == "text-embedding-3-small"
            assert kwargs["input"] == ["first", "second"]
            return SimpleNamespace(
                data=[
                    SimpleNamespace(index=1, embedding=[2.0]),
                    SimpleNamespace(index=0, embedding=[1.0]),
                ]
            )

    class FakeCompletions:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["response_format"] is ExtractedThoughtMetadata
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=ExtractedThoughtMetadata(summary="Structured result")
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(
        embeddings=FakeEmbeddings(),
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    provider = OpenAIProvider(Settings(openai_api_key="test"), client=fake_client)

    assert provider.embed(["first", "second"]) == [[1.0], [2.0]]
    assert provider.extract_metadata("A thought").summary == "Structured result"


def test_ai_disabled_thought_does_not_enqueue_or_create_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    def fail_enqueue(*args: object, **kwargs: object) -> None:
        raise AssertionError("AI-disabled thoughts must not be enqueued")

    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", fail_enqueue)

    response = client.post("/thoughts", json={"body": "No AI for this thought."})

    assert response.status_code == 201
    assert response.json()["ai_processing_status"] == AIProcessingStatus.NOT_REQUESTED.value
    assert db_session.scalars(select(BackgroundJob)).all() == []
    assert db_session.scalars(select(ThoughtChunk)).all() == []


def test_ai_enabled_thought_creates_pending_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)

    response = client.post(
        "/thoughts",
        json={"body": "Send this thought through Ask My Mind.", "use_with_ask_my_mind": True},
    )

    assert response.status_code == 201
    assert response.json()["ai_processing_status"] == AIProcessingStatus.PENDING.value
    jobs = db_session.scalars(select(BackgroundJob)).all()
    assert len(jobs) == 1
    assert jobs[0].status == BackgroundJobStatus.PENDING.value


def test_worker_creates_chunks_embeddings_and_metadata(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={
            "body": "A thought about testing and reliable systems.",
            "use_with_ask_my_mind": True,
        },
    )
    thought_id = UUID(response.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    process_ai_job(
        db_session,
        job.id,
        thought_id,
        provider_factory=lambda: FakeAIProvider(),
    )

    thought = db_session.get(Thought, thought_id)
    assert thought is not None
    assert thought.ai_processing_status == AIProcessingStatus.READY.value
    chunks = db_session.scalars(select(ThoughtChunk)).all()
    metadata = db_session.scalar(select(ThoughtMetadata))
    assert len(chunks) == 1
    assert chunks[0].embedding == [0.0, 1.0, 2.0]
    assert metadata is not None
    assert metadata.summary == "A focused test thought."
    assert metadata.themes == ["testing"]


def test_disabling_ai_purges_derived_artifacts(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={"body": "This thought will become private from AI.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(response.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None
    process_ai_job(db_session, job.id, thought_id, provider_factory=lambda: FakeAIProvider())

    update_response = client.patch(
        f"/thoughts/{thought_id}",
        json={"use_with_ask_my_mind": False},
    )

    assert update_response.status_code == 200
    assert update_response.json()["ai_processing_status"] == AIProcessingStatus.NOT_REQUESTED.value
    assert db_session.scalars(select(ThoughtChunk)).all() == []
    assert db_session.scalars(select(ThoughtMetadata)).all() == []
    assert db_session.scalar(select(BackgroundJob)).status == BackgroundJobStatus.COMPLETED.value


def test_openai_failure_does_not_undo_thought_save(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={
            "body": "The original thought must survive an AI outage.",
            "use_with_ask_my_mind": True,
        },
    )
    thought_id = UUID(response.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    def failing_provider():
        raise RuntimeError("provider unavailable")

    process_ai_job(db_session, job.id, thought_id, provider_factory=failing_provider)

    thought = db_session.get(Thought, thought_id)
    assert thought is not None
    assert thought.body == "The original thought must survive an AI outage."
    assert thought.ai_processing_status == AIProcessingStatus.FAILED.value
    assert job.status == BackgroundJobStatus.FAILED.value
    assert job.error_message == "RuntimeError"
