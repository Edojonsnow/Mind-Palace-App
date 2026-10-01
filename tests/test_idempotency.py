from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Event
from unittest.mock import Mock

import pytest
from fastapi import HTTPException, Response
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.request_errors import RequestNotStartedError
from app.db.base import Base
from app.models import ChatMessage, ExportRequest, IdempotencyRequest, Thought, User
from app.services.accounts import purge_user_data
from app.services.idempotency import complete_operation, execute_idempotent
from app.services.openai_ai import AIProviderError, GeneratedAskAnswer
from tests.test_ask import add_ready_thought, current_user

KEY = {"Idempotency-Key": "same-action"}


def test_thought_replay_conflict_and_distinct_actions(client, db_session):
    payload = {"body": "A private thought", "use_with_ask_my_mind": False}
    first = client.post("/thoughts", json=payload, headers=KEY)
    second = client.post("/thoughts", json=payload, headers=KEY)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert second.headers["Idempotency-Replayed"] == "true"
    assert client.post("/thoughts", json={"body": "Different"}, headers=KEY).status_code == 409
    client.post("/thoughts", json=payload, headers={"Idempotency-Key": "new-action"})
    assert db_session.scalar(select(func.count()).select_from(Thought)) == 2
    operation = db_session.scalar(select(IdempotencyRequest))
    assert operation.request_hash != payload["body"]
    assert not hasattr(operation, "response_body")


def test_thought_replay_does_not_recreate_deleted_result(client):
    payload = {"body": "Thought to delete"}
    thought_id = client.post("/thoughts", json=payload, headers=KEY).json()["id"]
    client.delete(f"/thoughts/{thought_id}")
    assert client.post("/thoughts", json=payload, headers=KEY).status_code == 410
    assert client.get("/thoughts").json() == []


def test_idempotency_is_user_scoped_and_purged(client, db_session):
    first = client.post("/thoughts", json={"body": "One"}, headers=KEY).json()
    original = client.app.dependency_overrides[get_current_user]
    client.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(
        auth_user_id="second", email="second@example.test",
    )
    try:
        second = client.post("/thoughts", json={"body": "Two"}, headers=KEY).json()
        user = db_session.scalar(select(User).where(User.auth_user_id == "second"))
        purge_user_data(db_session, user)
        db_session.commit()
    finally:
        client.app.dependency_overrides[get_current_user] = original
    assert first["id"] != second["id"]
    assert db_session.scalar(select(func.count()).select_from(IdempotencyRequest)) == 1


def test_ask_replays_without_duplicate_chat_or_provider_calls(client, db_session, monkeypatch):
    client.get("/settings")
    thought = add_ready_thought(db_session, current_user(db_session), "A cited thought")
    provider = Mock()
    provider.embed.return_value = [[1.0, 0.0, 0.0]]
    provider.answer_question.return_value = GeneratedAskAnswer(
        answer="Answer [S1]", citation_ids=["S1"],
    )
    monkeypatch.setattr("app.services.ask.OpenAIProvider", lambda: provider)
    payload = {"question": "What do I remember?"}
    first = client.post("/ask", json=payload, headers=KEY)
    second = client.post("/ask", json=payload, headers=KEY)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert provider.embed.call_count == provider.answer_question.call_count == 1
    assert db_session.scalar(select(func.count()).select_from(ChatMessage)) == 2
    client.patch(f"/thoughts/{thought.id}", json={"use_with_ask_my_mind": False})
    replay = client.post("/ask", json=payload, headers=KEY)
    assert replay.json()["sources"] == []
    assert provider.answer_question.call_count == 1


def test_ask_failure_does_not_retry_an_uncertain_provider_call(client, db_session, monkeypatch):
    client.get("/settings")
    add_ready_thought(db_session, current_user(db_session), "Source")
    provider = Mock()
    provider.embed.return_value = [[1.0, 0.0, 0.0]]
    provider.answer_question.side_effect = AIProviderError("Provider failed")
    monkeypatch.setattr("app.services.ask.OpenAIProvider", lambda: provider)
    first = client.post("/ask", json={"question": "Ask"}, headers=KEY)
    replay = client.post("/ask", json={"question": "Ask"}, headers=KEY)
    assert first.status_code == 503
    assert replay.status_code == 409
    assert provider.answer_question.call_count == 1
    assert db_session.scalar(select(func.count()).select_from(ChatMessage)) == 1


def test_history_off_does_not_store_answers_for_replay(client, db_session):
    client.patch("/settings", json={"store_chat_history": False})
    assert client.post("/ask", json={"question": "Ask"}, headers=KEY).status_code == 200
    assert client.post("/ask", json={"question": "Ask"}, headers=KEY).status_code == 409
    assert db_session.scalar(select(func.count()).select_from(ChatMessage)) == 0


def test_exports_replay_one_job(client, db_session, monkeypatch):
    enqueue = Mock()
    monkeypatch.setattr("app.core.queue.enqueue_export_generation", enqueue)
    first = client.post("/exports", headers=KEY)
    second = client.post("/exports", headers=KEY)
    assert first.status_code == second.status_code == 202
    assert first.json()["id"] == second.json()["id"]
    assert db_session.scalar(select(func.count()).select_from(ExportRequest)) == 1
    enqueue.assert_called_once()


def test_organization_replay_enqueues_once(client, monkeypatch):
    enqueue = Mock()
    monkeypatch.setattr("app.services.ai_processing.enqueue_ai_processing", enqueue)
    thought = client.post("/thoughts", json={"body": "Source", "use_with_ask_my_mind": True}).json()
    enqueue.reset_mock()
    url = f"/thoughts/{thought['id']}/organize"
    assert client.post(url, headers=KEY).status_code == 200
    assert client.post(url, headers=KEY).status_code == 200
    enqueue.assert_called_once()


def test_completed_requests_expire_but_uncertain_claims_do_not(client, db_session):
    client.post("/thoughts", json={"body": "Source"}, headers=KEY)
    operation = db_session.scalar(select(IdempotencyRequest))
    operation.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    client.post("/thoughts", json={"body": "Source"}, headers=KEY)
    assert db_session.scalar(select(func.count()).select_from(Thought)) == 2
    operation = db_session.scalar(select(IdempotencyRequest))
    operation.status = "uncertain"
    operation.expires_at = datetime.now(UTC) - timedelta(hours=1)
    db_session.commit()
    assert client.post("/thoughts", json={"body": "Source"}, headers=KEY).status_code == 409


@pytest.mark.parametrize("key", ["", "x" * 129, "has spaces"])
def test_invalid_keys_are_rejected(client, key):
    assert client.post("/thoughts", json={"body": "Source"}, headers={
        "Idempotency-Key": key,
    }).status_code == 422


def test_admission_rejection_releases_key_without_side_effects(client, db_session):
    client.get("/settings")
    user = current_user(db_session)
    def deny(operation):
        raise RequestNotStartedError(429, "Wait", headers={"Retry-After": "1"})
    with pytest.raises(RequestNotStartedError):
        execute_idempotent(db_session, user, "POST /ask", "key", {}, Response(), deny)
    assert db_session.scalar(select(func.count()).select_from(IdempotencyRequest)) == 0


def test_concurrent_claims_allow_only_one_action(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'claims.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(auth_user_id="concurrent", email="concurrent@example.test")
        db.add(user)
        db.commit()
        user_id = user.id
    entered, release = Event(), Event()
    calls = []
    def invoke():
        with Session(engine) as db:
            user = db.get(User, user_id)
            def action(operation):
                calls.append(1)
                entered.set()
                assert release.wait(5)
                complete_operation(operation, "unstored_answer", None)
                return "done"
            try:
                return execute_idempotent(db, user, "POST /ask", "key", {}, Response(), action)
            except HTTPException as error:
                return error.status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(invoke)
        try:
            assert entered.wait(5)
            assert pool.submit(invoke).result(timeout=5) == 409
        finally:
            release.set()
        assert first.result(timeout=5) == "done"
    assert calls == [1]
    engine.dispose()
