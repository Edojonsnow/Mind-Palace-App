from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from redis.exceptions import ConnectionError
from sqlalchemy import func, select

from app.core.config import Settings, settings
from app.core.rate_limit import enforce_rate_limit
from app.core.request_errors import RequestNotStartedError
from app.models import BackgroundJob, ChatMessage, ExportRequest, IdempotencyRequest, Thought
from app.services.ai_processing import process_ai_job
from tests.test_ai_processing import FakeAIProvider


def test_shared_limiter_returns_retry_after_and_scopes_buckets(monkeypatch):
    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    connection = Mock()
    connection.eval.side_effect = [[1, 60_000], [0, 12_001], [1, 60_000]]
    monkeypatch.setattr("app.core.rate_limit.get_redis_connection", lambda: connection)
    user_id = uuid4()
    enforce_rate_limit(user_id, "ask")
    with pytest.raises(RequestNotStartedError) as denied:
        enforce_rate_limit(user_id, "ask")
    assert denied.value.status_code == 429
    assert denied.value.headers["Retry-After"] == "13"
    enforce_rate_limit(uuid4(), "semantic_search")
    first, _, third = connection.eval.call_args_list
    assert first.args[2] == f"mind-palace:rate:ask:{user_id}"
    assert third.args[2] != first.args[2]
    assert first.args[3:] == (10, 60_000)


def test_redis_outage_fails_closed_for_expensive_requests(monkeypatch):
    monkeypatch.setattr(settings, "rate_limits_enabled", True)
    connection = Mock()
    connection.eval.side_effect = ConnectionError("Redis unavailable")
    monkeypatch.setattr("app.core.rate_limit.get_redis_connection", lambda: connection)
    with pytest.raises(RequestNotStartedError) as denied:
        enforce_rate_limit(uuid4(), "ask")
    assert denied.value.status_code == 503
    assert denied.value.headers["Retry-After"] == "30"


def test_disabled_limiter_does_not_connect(monkeypatch):
    connect = Mock(side_effect=AssertionError("No Redis in disabled mode"))
    monkeypatch.setattr("app.core.rate_limit.get_redis_connection", connect)
    enforce_rate_limit(uuid4(), "ask")
    connect.assert_not_called()


def test_limits_must_be_positive():
    with pytest.raises(ValueError):
        Settings(rate_limit_ask_per_minute=0)


def denied(*args):
    raise RequestNotStartedError(429, "Questions limit reached. Try again in 10 seconds.",
                                 headers={"Retry-After": "10"})


@pytest.mark.parametrize("status_code", [429, 503])
def test_ask_admission_blocks_side_effects_and_same_key_can_retry(
    client, db_session, monkeypatch, status_code,
):
    admission = Mock(side_effect=RequestNotStartedError(
        status_code, "Wait", headers={"Retry-After": "10"},
    ))
    monkeypatch.setattr("app.services.ask.enforce_rate_limit", admission)
    payload, headers = {"question": "A question"}, {"Idempotency-Key": "rate-test"}
    blocked = client.post("/ask", json=payload, headers=headers)
    assert blocked.status_code == status_code
    assert blocked.headers["Retry-After"] == "10"
    assert db_session.scalar(select(func.count()).select_from(ChatMessage)) == 0
    assert db_session.scalar(select(func.count()).select_from(IdempotencyRequest)) == 0
    admission.side_effect = None
    assert client.post("/ask", json=payload, headers=headers).status_code == 200
    admission.side_effect = denied
    assert client.post("/ask", json=payload, headers=headers).status_code == 200
    assert admission.call_count == 2


def test_exports_are_limited_before_job_creation(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.exports.enforce_rate_limit", denied)
    response = client.post("/exports", headers={"Idempotency-Key": "export-test"})
    assert response.status_code == 429
    assert db_session.scalar(select(func.count()).select_from(ExportRequest)) == 0
    assert db_session.scalar(select(func.count()).select_from(BackgroundJob)) == 0


def test_semantic_limits_fall_back_to_text_and_browsing_does_not_consume_allowance(
    client, monkeypatch,
):
    monkeypatch.setattr(settings, "openai_api_key", "test")
    admission = Mock(side_effect=denied)
    provider = Mock()
    monkeypatch.setattr("app.api.routes.thoughts.enforce_rate_limit", admission)
    monkeypatch.setattr("app.api.routes.thoughts.OpenAIProvider", provider)
    client.post("/thoughts", json={"body": "Tennis is fun"})
    client.post("/thoughts", json={"body": "Unrelated"})
    result = client.get("/thoughts?q=tennis")
    assert result.status_code == 200
    assert result.headers["X-Search-Fallback"] == "rate-limit"
    assert [thought["body"] for thought in result.json()] == ["Tennis is fun"]
    provider.assert_not_called()
    client.get("/thoughts")
    admission.assert_called_once()


def test_search_remains_usable_when_redis_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "test")
    admission = Mock(side_effect=RequestNotStartedError(
        503, "Unavailable", headers={"Retry-After": "30"},
    ))
    monkeypatch.setattr("app.api.routes.thoughts.enforce_rate_limit", admission)
    result = client.get("/thoughts?q=tennis")
    assert result.status_code == 200
    assert result.headers["X-Search-Fallback"] == "unavailable"


def test_processing_defers_without_losing_capture_and_resumes_once(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    deferred = Mock()
    monkeypatch.setattr("app.services.ai_processing.enqueue_deferred_ai_processing", deferred)
    admission = Mock(side_effect=denied)
    monkeypatch.setattr("app.services.ai_processing.enforce_rate_limit", admission)
    provider = Mock(return_value=FakeAIProvider())
    created = client.post("/thoughts", json={"body": "Saved", "use_with_ask_my_mind": True})
    assert created.status_code == 201
    thought_id = UUID(created.json()["id"])
    job = db_session.scalar(select(BackgroundJob).where(BackgroundJob.thought_id == thought_id))
    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)
    assert job.status == "pending" and job.attempt_count == 0 and job.not_before is not None
    assert db_session.get(Thought, thought_id).body == "Saved"
    provider.assert_not_called()
    deferred.assert_called_once()
    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)
    assert admission.call_count == 1
    job.not_before = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    admission.side_effect = None
    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)
    assert job.status == "completed" and job.attempt_count == 1 and job.not_before is None
    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)
    provider.assert_called_once()


def test_ai_opt_out_bypasses_limits_and_cancels_deferred_work(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    thought = client.post("/thoughts", json={"body": "Saved", "use_with_ask_my_mind": True}).json()
    job = db_session.scalar(select(BackgroundJob))
    job.not_before = datetime.now(UTC) + timedelta(minutes=1)
    db_session.commit()
    admission = Mock(side_effect=denied)
    monkeypatch.setattr("app.services.thoughts.enforce_rate_limit", admission)
    assert client.post(f"/thoughts/{thought['id']}/organize").status_code == 429
    response = client.patch(
        f"/thoughts/{thought['id']}", json={"use_with_ask_my_mind": False},
    )
    assert response.status_code == 200
    assert job.status == "cancelled"
    admission.assert_called_once()


def test_failed_deferred_enqueue_keeps_original_thought(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    monkeypatch.setattr("app.services.ai_processing.enforce_rate_limit", denied)
    monkeypatch.setattr("app.services.ai_processing.enqueue_deferred_ai_processing", Mock(
        side_effect=ConnectionError("Redis unavailable"),
    ))
    thought = client.post("/thoughts", json={"body": "Saved", "use_with_ask_my_mind": True}).json()
    job = db_session.scalar(select(BackgroundJob))
    process_ai_job(db_session, job.id, UUID(thought["id"]))
    assert job.status == "pending"
    assert job.not_before is not None
    assert job.error_message == "ConnectionError"
    assert client.get(f"/thoughts/{thought['id']}").json()["body"] == "Saved"


def test_deferred_job_discards_changed_content_before_ai_admission(
    client, db_session, monkeypatch,
):
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    created = client.post("/thoughts", json={"body": "Old", "use_with_ask_my_mind": True}).json()
    thought_id = UUID(created["id"])
    job = db_session.scalar(select(BackgroundJob))
    db_session.get(Thought, thought_id).body = "Changed while waiting"
    job.not_before = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()
    admission, provider = Mock(), Mock()
    monkeypatch.setattr("app.services.ai_processing.enforce_rate_limit", admission)
    process_ai_job(db_session, job.id, thought_id, provider_factory=provider)
    assert job.status == "cancelled" and job.attempt_count == 0
    admission.assert_not_called()
    provider.assert_not_called()


def test_job_cannot_process_another_thought(client, db_session, monkeypatch):
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", Mock())
    client.post("/thoughts", json={"body": "First", "use_with_ask_my_mind": True})
    job = db_session.scalar(select(BackgroundJob))
    second = client.post("/thoughts", json={"body": "Second"}).json()
    admission, provider = Mock(), Mock()
    monkeypatch.setattr("app.services.ai_processing.enforce_rate_limit", admission)
    process_ai_job(db_session, job.id, UUID(second["id"]), provider_factory=provider)
    admission.assert_not_called()
    provider.assert_not_called()
