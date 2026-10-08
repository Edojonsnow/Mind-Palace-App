from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import select

from app.core.ai_quota import AIQuotaExceededError, reserve_ai_quota
from app.core.config import settings
from app.models import AIUsageDaily, BackgroundJob, ChatMessage, ThoughtChunk
from app.services.ai_processing import process_ai_job
from tests.test_ai_processing import FakeAIProvider
from tests.test_ask import add_ready_thought, current_user


def test_daily_quota_reservation_is_atomic_and_tracks_operation_counts(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "ai_daily_quota_units", 3)
    client.get("/settings")
    user = current_user(db_session)

    reserve_ai_quota(db_session, user.id, "ask", units=2)
    db_session.commit()
    reserve_ai_quota(db_session, user.id, "search", units=1)
    db_session.commit()

    usage = db_session.scalar(select(AIUsageDaily))
    assert usage is not None
    assert usage.units_used == 3
    assert usage.ask_count == 1
    assert usage.search_count == 1

    with pytest.raises(AIQuotaExceededError) as error:
        reserve_ai_quota(db_session, user.id, "organization", units=2)
    assert error.value.status_code == 429
    assert error.value.headers["X-AI-Quota"] == "daily"


def test_ask_quota_denial_happens_before_chat_history_or_provider_call(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "ai_daily_quota_units", 1)
    client.get("/settings")
    thought = add_ready_thought(
        db_session,
        current_user(db_session),
        "A thought that can answer a question.",
    )
    provider = Mock()
    monkeypatch.setattr("app.services.ask.OpenAIProvider", lambda: provider)

    response = client.post("/ask", json={"question": "What do I remember?"})

    assert response.status_code == 429
    assert response.headers["Retry-After"]
    assert db_session.scalars(select(ChatMessage)).all() == []
    assert db_session.get(ThoughtChunk, thought.chunks[0].id) is not None
    provider.assert_not_called()


def test_usage_endpoint_reports_remaining_daily_units(client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "ai_daily_quota_units", 5)
    client.get("/settings")
    user = current_user(db_session)
    reserve_ai_quota(db_session, user.id, "search", units=1)
    db_session.commit()

    response = client.get("/settings/ai-usage")

    assert response.status_code == 200
    assert response.json()["units_used"] == 1
    assert response.json()["remaining_units"] == 4
    assert response.json()["search_count"] == 1


def test_semantic_search_uses_lexical_fallback_when_daily_quota_is_exhausted(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "openai_api_key", "test")
    monkeypatch.setattr(settings, "ai_daily_quota_units", 1)
    client.get("/settings")
    user = current_user(db_session)
    reserve_ai_quota(db_session, user.id, "search", units=1)
    db_session.commit()
    provider = Mock()
    monkeypatch.setattr("app.api.routes.thoughts.OpenAIProvider", provider)
    created = client.post("/thoughts", json={"body": "Tennis is fun"})
    assert created.status_code == 201
    db_session.commit()

    response = client.get("/thoughts?q=tennis&search_mode=semantic")

    assert response.status_code == 200
    assert response.headers["X-Search-Fallback"] == "quota"
    assert [thought["body"] for thought in response.json()] == ["Tennis is fun"]
    provider.assert_not_called()


def test_keyword_search_is_default_and_does_not_use_ai_quota_or_provider(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "openai_api_key", "test")
    provider = Mock()
    monkeypatch.setattr("app.api.routes.thoughts.OpenAIProvider", provider)
    created = client.post("/thoughts", json={"body": "Tennis is fun"})
    assert created.status_code == 201

    response = client.get("/thoughts?q=tennis")

    assert response.status_code == 200
    assert response.headers["X-Search-Mode"] == "keyword"
    assert "X-Search-Fallback" not in response.headers
    assert [thought["body"] for thought in response.json()] == ["Tennis is fun"]
    assert db_session.scalar(select(AIUsageDaily)) is None
    provider.assert_not_called()


def test_worker_defers_organization_until_daily_quota_resets(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr(settings, "ai_daily_quota_units", 2)
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    deferred = Mock()
    monkeypatch.setattr("app.services.ai_processing.enqueue_deferred_ai_processing", deferred)
    thought_response = client.post(
        "/thoughts", json={"body": "Queue this thought", "use_with_ask_my_mind": True},
    )
    thought_id = UUID(thought_response.json()["id"])
    job = db_session.scalar(select(BackgroundJob).where(BackgroundJob.thought_id == thought_id))
    user = current_user(db_session)
    reserve_ai_quota(db_session, user.id, "organization", units=2)
    db_session.commit()
    provider = Mock(return_value=FakeAIProvider())

    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)

    assert job.status == "pending"
    assert job.not_before is not None
    provider.assert_not_called()
    deferred.assert_called_once()


def test_ai_enabled_thoughts_are_rejected_above_configured_size(client, monkeypatch):
    monkeypatch.setattr(settings, "ai_max_thought_chars", 10)

    response = client.post(
        "/thoughts",
        json={"body": "This thought is too long", "use_with_ask_my_mind": True},
    )

    assert response.status_code == 413
