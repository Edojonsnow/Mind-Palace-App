from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, settings
from app.models import (
    AIProcessingStatus,
    BackgroundJob,
    BackgroundJobStatus,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
)
from app.services.ai_processing import (
    normalize_extracted_metadata,
    process_ai_job,
    schedule_ai_processing,
)
from app.services.ai_processing_content import AI_ENRICHMENT_SCHEMA_VERSION, semantic_text
from app.services.ai_recovery import reconcile_ai_jobs
from app.services.openai_ai import (
    ExtractedThoughtMetadata,
    GeneratedAskAnswer,
    OpenAIProvider,
)


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


def test_semantic_text_includes_capture_context() -> None:
    thought = Thought(
        title="A useful title",
        body="The body of the thought.",
        source_type="book",
        source_title="A source",
        source_author="An author",
        book_title="A book",
        book_author="A book author",
        page_reference="42",
        manual_tags=["focus", "reading"],
    )

    enriched = semantic_text(thought)

    assert "Title: A useful title" in enriched
    assert "Thought: The body of the thought." in enriched
    assert "Book: A book" in enriched
    assert "Tags: focus, reading" in enriched


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


def test_extracted_metadata_keeps_open_ended_themes_and_normalizes_values() -> None:
    with pytest.raises(ValueError):
        ExtractedThoughtMetadata(themes=["one", "two", "three", "four", "five", "six"])

    metadata = normalize_extracted_metadata(
        ExtractedThoughtMetadata(
            themes=["career development", "Work", "  Work  "],
            emotions=["happy", "Joy"],
            people=[" Alex ", "Alex", "James Clear"],
            books=[" Deep Work ", "Deep Work", "Atomic Habits"],
        )
    )

    assert metadata.themes == ["career development", "Work"]
    assert metadata.emotions == ["happy", "Joy"]
    assert metadata.people == ["Alex", "James Clear"]
    assert metadata.books == ["Deep Work", "Atomic Habits"]


def test_openai_provider_adapts_structured_ask_answer() -> None:
    class FakeCompletions:
        def parse(self, **kwargs: object) -> SimpleNamespace:
            assert kwargs["model"] == "gpt-4.1-mini"
            assert kwargs["response_format"] is GeneratedAskAnswer
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(
                            parsed=GeneratedAskAnswer(
                                answer="A grounded answer [S1]",
                                citation_ids=["S1"],
                            )
                        )
                    )
                ]
            )

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=FakeCompletions()),
    )
    provider = OpenAIProvider(Settings(openai_api_key="test"), client=fake_client)

    answer = provider.answer_question(
        "What matters?",
        "[S1] Protect focused work.",
        [],
    )

    assert answer.answer == "A grounded answer [S1]"
    assert answer.citation_ids == ["S1"]


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


def test_initial_queue_failure_keeps_ai_job_recoverable(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "app.services.ai_processing.enqueue_ai_processing",
        Mock(side_effect=ConnectionError("Redis unavailable")),
    )

    response = client.post(
        "/thoughts",
        json={
            "body": "Keep this capture while the queue is unavailable.",
            "use_with_ask_my_mind": True,
        },
    )

    job = db_session.scalar(select(BackgroundJob))
    thought = db_session.get(Thought, UUID(response.json()["id"]))
    assert job is not None
    assert thought is not None
    assert response.status_code == 201
    assert job.status == BackgroundJobStatus.PENDING.value
    assert job.error_message == "ConnectionError"
    assert job.not_before is not None
    assert thought.ai_processing_status == AIProcessingStatus.PENDING.value


def test_reconciler_requeues_a_stranded_pending_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    created = client.post(
        "/thoughts",
        json={"body": "This job committed before Redis dispatch.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(created.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    enqueue = Mock()
    monkeypatch.setattr("app.services.ai_recovery.enqueue_ai_processing", enqueue)
    result = reconcile_ai_jobs(db_session, now=datetime.now(UTC))

    assert result.requeued == 1
    assert result.stale_recovered == 0
    enqueue.assert_called_once_with(job.id, thought_id)
    db_session.expire_all()
    recovered = db_session.get(BackgroundJob, job.id)
    assert recovered is not None
    assert recovered.status == BackgroundJobStatus.PENDING.value
    assert recovered.not_before is None
    assert recovered.error_message is None


def test_reconciler_reclaims_a_stale_running_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    created = client.post(
        "/thoughts",
        json={"body": "A worker died during this job.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(created.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None
    now = datetime.now(UTC)
    job.status = BackgroundJobStatus.RUNNING.value
    job.started_at = now - timedelta(seconds=settings.ai_job_stale_after_seconds + 1)
    db_session.commit()

    enqueue = Mock()
    monkeypatch.setattr("app.services.ai_recovery.enqueue_ai_processing", enqueue)
    result = reconcile_ai_jobs(db_session, now=now)

    assert result.requeued == 1
    assert result.stale_recovered == 1
    enqueue.assert_called_once_with(job.id, thought_id)
    db_session.expire_all()
    recovered = db_session.get(BackgroundJob, job.id)
    assert recovered is not None
    assert recovered.status == BackgroundJobStatus.PENDING.value
    assert recovered.started_at is None


def test_reconciler_does_not_touch_a_fresh_running_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    client.post(
        "/thoughts",
        json={"body": "A worker is still processing this.", "use_with_ask_my_mind": True},
    )
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None
    now = datetime.now(UTC)
    job.status = BackgroundJobStatus.RUNNING.value
    job.started_at = now - timedelta(seconds=settings.ai_job_stale_after_seconds - 1)
    db_session.commit()

    enqueue = Mock()
    monkeypatch.setattr("app.services.ai_recovery.enqueue_ai_processing", enqueue)
    result = reconcile_ai_jobs(db_session, now=now)

    assert result.requeued == 0
    assert result.stale_recovered == 0
    enqueue.assert_not_called()
    assert job.status == BackgroundJobStatus.RUNNING.value


def test_reconciler_keeps_dispatch_failure_pending_for_retry(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    client.post(
        "/thoughts",
        json={"body": "Retry dispatch without losing this thought.", "use_with_ask_my_mind": True},
    )
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    monkeypatch.setattr(
        "app.services.ai_recovery.enqueue_ai_processing",
        Mock(side_effect=ConnectionError("Redis unavailable")),
    )
    result = reconcile_ai_jobs(db_session, now=datetime.now(UTC))

    assert result.requeued == 0
    assert result.dispatch_failures == 1
    db_session.expire_all()
    pending = db_session.get(BackgroundJob, job.id)
    assert pending is not None
    assert pending.status == BackgroundJobStatus.PENDING.value
    assert pending.not_before is not None
    assert pending.error_message == "ConnectionError"


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
    assert metadata.enrichment_schema_version == AI_ENRICHMENT_SCHEMA_VERSION
    assert metadata.metadata_model == settings.openai_metadata_model
    assert metadata.source_hash is not None
    assert metadata.processed_at is not None
    assert chunks[0].enrichment_schema_version == AI_ENRICHMENT_SCHEMA_VERSION
    assert chunks[0].embedding_model == settings.openai_embedding_model
    assert chunks[0].source_hash == metadata.source_hash
    assert job.enrichment_schema_version == AI_ENRICHMENT_SCHEMA_VERSION
    assert job.embedding_model == settings.openai_embedding_model
    assert job.metadata_model == settings.openai_metadata_model
    assert job.source_hash == metadata.source_hash


def test_completed_ai_job_is_idempotent(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={"body": "Run this enrichment once.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(response.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    calls = {"embed": 0, "metadata": 0}

    class CountingProvider(FakeAIProvider):
        def embed(self, texts: list[str]) -> list[list[float]]:
            calls["embed"] += 1
            return super().embed(texts)

        def extract_metadata(self, thought_body: str) -> ExtractedThoughtMetadata:
            calls["metadata"] += 1
            return super().extract_metadata(thought_body)

    process_ai_job(
        db_session,
        job.id,
        thought_id,
        provider_factory=lambda: CountingProvider(),
    )
    process_ai_job(
        db_session,
        job.id,
        thought_id,
        provider_factory=lambda: CountingProvider(),
    )

    db_session.expire_all()
    assert calls == {"embed": 1, "metadata": 1}
    assert len(db_session.scalars(select(ThoughtChunk)).all()) == 1
    assert len(db_session.scalars(select(ThoughtMetadata)).all()) == 1
    assert db_session.scalar(select(BackgroundJob)).attempt_count == 1


def test_scheduling_reuses_an_active_enrichment_job(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={"body": "Do not duplicate pending work.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(response.json()["id"])
    thought = db_session.get(Thought, thought_id)
    assert thought is not None
    first_job = db_session.scalar(select(BackgroundJob))
    assert first_job is not None

    second_job = schedule_ai_processing(db_session, thought)

    assert second_job.id == first_job.id
    assert len(db_session.scalars(select(BackgroundJob)).all()) == 1


def test_worker_discards_results_for_changed_source_content(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={"body": "The source before processing.", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(response.json()["id"])
    job = db_session.scalar(select(BackgroundJob))
    assert job is not None

    class StaleResultProvider(FakeAIProvider):
        def embed(self, texts: list[str]) -> list[list[float]]:
            thought = db_session.get(Thought, thought_id)
            assert thought is not None
            thought.body = "The source changed while processing."
            db_session.commit()
            return super().embed(texts)

    process_ai_job(
        db_session,
        job.id,
        thought_id,
        provider_factory=lambda: StaleResultProvider(),
    )

    db_session.expire_all()
    assert db_session.scalar(select(BackgroundJob)).status == BackgroundJobStatus.CANCELLED.value
    assert db_session.scalars(select(ThoughtChunk)).all() == []
    assert db_session.scalars(select(ThoughtMetadata)).all() == []


def test_editing_organization_fields_purges_stale_artifacts_and_reschedules(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", no_op_enqueue)
    response = client.post(
        "/thoughts",
        json={
            "body": "A thought with an original tag.",
            "manual_tags": ["original"],
            "use_with_ask_my_mind": True,
        },
    )
    thought_id = UUID(response.json()["id"])
    first_job = db_session.scalar(select(BackgroundJob))
    assert first_job is not None
    process_ai_job(db_session, first_job.id, thought_id, provider_factory=lambda: FakeAIProvider())

    update_response = client.patch(
        f"/thoughts/{thought_id}",
        json={"manual_tags": ["edited"]},
    )

    assert update_response.status_code == 200
    assert update_response.json()["ai_processing_status"] == AIProcessingStatus.PENDING.value
    assert db_session.scalars(select(ThoughtChunk)).all() == []
    assert db_session.scalars(select(ThoughtMetadata)).all() == []

    pending_job = db_session.scalar(
        select(BackgroundJob).where(BackgroundJob.status == BackgroundJobStatus.PENDING.value)
    )
    assert pending_job is not None
    process_ai_job(
        db_session,
        pending_job.id,
        thought_id,
        provider_factory=lambda: FakeAIProvider(),
    )

    metadata = db_session.scalar(select(ThoughtMetadata))
    assert metadata is not None
    assert metadata.deterministic_metadata["manual_tags"] == ["edited"]


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
