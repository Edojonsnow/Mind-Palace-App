from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountDeletionRequest,
    BackgroundJob,
    ChatConversation,
    ChatMessage,
    ChatMessageRole,
    ExportRequest,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
    User,
)
from app.services.accounts import process_account_deletion
from app.services.data_lifecycle import purge_expired_thoughts
from app.services.exports import process_export


def current_user(db_session: Session) -> User:
    user = db_session.scalar(select(User).where(User.auth_user_id == "test-auth-user"))
    assert user is not None
    return user


def test_deleted_thought_can_be_listed_and_restored(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.queue.enqueue_thought_purge", lambda *args: None)
    create_response = client.post("/thoughts", json={"body": "Restore this thought."})
    thought_id = UUID(create_response.json()["id"])

    assert client.delete(f"/thoughts/{thought_id}").status_code == 204
    deleted_response = client.get("/thoughts/deleted")

    assert deleted_response.status_code == 200
    assert deleted_response.json()[0]["id"] == str(thought_id)
    assert deleted_response.json()[0]["purge_at"] is not None

    restore_response = client.post(f"/thoughts/{thought_id}/restore")

    assert restore_response.status_code == 200
    assert restore_response.json()["deleted_at"] is None
    assert restore_response.json()["purge_at"] is None
    assert client.get(f"/thoughts/{thought_id}").status_code == 200


def test_expired_thought_purge_removes_ai_artifacts_and_citations(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.queue.enqueue_thought_purge", lambda *args: None)
    create_response = client.post(
        "/thoughts",
        json={"body": "Remove this thought permanently.", "use_with_ask_my_mind": False},
    )
    thought_id = UUID(create_response.json()["id"])
    user = current_user(db_session)
    thought = db_session.get(Thought, thought_id)
    assert thought is not None
    thought.deleted_at = datetime.now(UTC) - timedelta(days=31)
    thought.purge_at = datetime.now(UTC) - timedelta(days=1)
    chunk = ThoughtChunk(
        user_id=user.id,
        thought_id=thought.id,
        chunk_text=thought.body,
        chunk_index=0,
        embedding=[1.0, 0.0, 0.0],
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.add(
        ThoughtMetadata(
            user_id=user.id,
            thought_id=thought.id,
            summary="Temporary summary",
            themes=[],
            emotions=[],
            people=[],
            places=[],
            books=[],
            key_questions=[],
            action_items=[],
            deterministic_metadata={},
        )
    )
    conversation = ChatConversation(user_id=user.id)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        ChatMessage(
            conversation_id=conversation.id,
            user_id=user.id,
            role=ChatMessageRole.ASSISTANT.value,
            content="A prior answer.",
            citations=[{"thought_id": str(thought.id), "chunk_id": str(chunk.id)}],
        )
    )
    db_session.commit()

    assert purge_expired_thoughts(db_session) == 1
    assert db_session.get(Thought, thought_id) is None
    assert db_session.scalars(select(ThoughtChunk)).all() == []
    assert db_session.scalars(select(ThoughtMetadata)).all() == []
    message = db_session.scalar(select(ChatMessage))
    assert message is not None
    assert message.citations == []


def test_export_is_generated_and_downloadable(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.queue.enqueue_export_generation", lambda *args: None)
    monkeypatch.setattr("app.core.queue.enqueue_export_expiry", lambda *args: None)
    client.post("/thoughts", json={"body": "Include this in the export."})

    create_response = client.post("/exports")

    assert create_response.status_code == 202
    export_id = UUID(create_response.json()["id"])
    export = db_session.get(ExportRequest, export_id)
    assert export is not None
    job = db_session.scalar(
        select(BackgroundJob).where(BackgroundJob.job_type == "generate_export")
    )
    assert job is not None

    process_export(db_session, export.id, job.id)

    status_response = client.get(f"/exports/{export_id}")
    download_response = client.get(f"/exports/{export_id}/download")
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert download_response.status_code == 200
    assert download_response.json()["thoughts"][0]["body"] == "Include this in the export."


def test_account_deletion_can_be_cancelled_and_resubmitted(
    client: TestClient,
    db_session: Session,
    monkeypatch,
) -> None:
    monkeypatch.setattr("app.core.queue.enqueue_account_deletion", lambda *args: None)

    first_response = client.post("/account/deletion")
    assert first_response.status_code == 202
    assert client.get("/account/deletion").json()["status"] == "pending"
    assert client.delete("/account/deletion").status_code == 204
    assert client.get("/account/deletion").json() is None

    second_response = client.post("/account/deletion")
    assert second_response.status_code == 202
    assert second_response.json()["status"] == "pending"

    request = db_session.get(AccountDeletionRequest, UUID(second_response.json()["id"]))
    assert request is not None
    request.purge_at = datetime.now(UTC) - timedelta(days=1)
    db_session.commit()
    user = current_user(db_session)

    process_account_deletion(db_session, request.id)

    assert db_session.get(User, user.id) is None
