from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.models import (
    AccountDeletionRequest,
    AIPreferences,
    BackgroundJob,
    Book,
    ChatConversation,
    ChatMessage,
    Collection,
    DeletedAuthIdentity,
    Thought,
    ThoughtChunk,
    ThoughtMetadata,
    User,
    UserSettings,
)
from app.models.collection import collection_thoughts
from app.services.accounts import process_account_deletion
from app.services.users import auth_identity_hash


@pytest.fixture
def permanent_client(client: TestClient, monkeypatch) -> TestClient:
    async def fresh_session():
        return AuthenticatedUser(
            auth_user_id="test-auth-user",
            email="alex@example.com",
            session_created_at=datetime.now(UTC),
        )

    client.app.dependency_overrides[get_current_user] = fresh_session
    monkeypatch.setattr(settings, "neon_api_key", "synthetic-key")
    monkeypatch.setattr(settings, "neon_project_id", "synthetic-project")
    monkeypatch.setattr(settings, "neon_auth_branch_id", "synthetic-branch")
    monkeypatch.setattr("app.services.accounts.delete_neon_auth_user", lambda *_: None)
    return client


def delete_now(client: TestClient):
    return client.post("/account/deletion/permanent", json={"confirmation": "DELETE MY ACCOUNT"})


def test_permanent_deletion_removes_owned_data_and_allows_new_signup(
    permanent_client: TestClient,
    db_session: Session,
):
    client = permanent_client
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    assert db_session.connection().exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
    book = client.post("/books", json={"title": "Synthetic book", "author": "Test Author"}).json()
    collection = client.post("/collections", json={"name": "Synthetic collection"}).json()
    response = client.post(
        "/thoughts",
        json={
            "body": "Synthetic test content.",
            "thought_type": "book_excerpt",
            "book_id": book["id"],
            "collection_ids": [collection["id"]],
        },
    )
    assert response.status_code == 201
    thought = db_session.get(Thought, UUID(response.json()["id"]))
    user = db_session.get(User, thought.user_id)
    user_id = user.id
    other = User(auth_user_id="other-user", email="other@example.test")
    db_session.add(other)
    db_session.flush()
    other_thought = Thought(user_id=other.id, body="Another account's synthetic note.")
    db_session.add(other_thought)
    db_session.add(
        ThoughtChunk(
            user_id=user_id,
            thought_id=thought.id,
            chunk_text="Synthetic",
            chunk_index=0,
            embedding=[1, 0, 0],
        )
    )
    db_session.add(ThoughtMetadata(user_id=user_id, thought_id=thought.id))
    db_session.add(BackgroundJob(user_id=user_id, thought_id=thought.id, job_type="embed_thought"))
    db_session.add(AIPreferences(user_id=user_id))
    conversation = ChatConversation(user_id=user_id)
    db_session.add(conversation)
    db_session.flush()
    db_session.add(
        ChatMessage(
            user_id=user_id,
            conversation_id=conversation.id,
            role="user",
            content="Synthetic conversation",
        )
    )
    db_session.commit()

    assert delete_now(client).status_code == 204
    for model in (
        UserSettings,
        Thought,
        ThoughtChunk,
        ThoughtMetadata,
        BackgroundJob,
        Book,
        Collection,
        ChatConversation,
        ChatMessage,
        AIPreferences,
        AccountDeletionRequest,
    ):
        assert db_session.scalars(select(model).where(model.user_id == user_id)).all() == []
    assert db_session.execute(select(collection_thoughts)).all() == []
    assert db_session.get(User, user_id) is None
    assert db_session.get(User, other.id) is not None
    assert db_session.get(Thought, other_thought.id) is not None
    tombstone = db_session.get(DeletedAuthIdentity, auth_identity_hash("test-auth-user"))
    assert tombstone is not None
    assert len(tombstone.auth_id_hash) == 64
    # An old, still correctly signed identity must never provision a fresh account.
    assert client.get("/settings").status_code == 401
    assert db_session.scalar(select(User).where(User.auth_user_id == "test-auth-user")) is None

    async def newly_signed_up():
        return AuthenticatedUser(auth_user_id="new-neon-id", email="alex@example.com")

    client.app.dependency_overrides[get_current_user] = newly_signed_up
    response = client.get("/settings")
    assert response.status_code == 200
    assert response.json()["onboarding_completed_at"] is None
    assert client.get("/thoughts").json() == []


@pytest.mark.parametrize("age", [None, 601, -120])
def test_permanent_deletion_requires_recent_provider_session(
    permanent_client: TestClient,
    monkeypatch,
    age,
):
    called = []
    monkeypatch.setattr(
        "app.services.accounts.delete_neon_auth_user",
        lambda *_: called.append(True),
    )

    async def stale_session():
        return AuthenticatedUser(
            auth_user_id="test-auth-user",
            email="alex@example.com",
            session_created_at=None if age is None else datetime.now(UTC) - timedelta(seconds=age),
        )

    permanent_client.app.dependency_overrides[get_current_user] = stale_session
    response = delete_now(permanent_client)
    assert response.status_code == 403
    assert "sign in again" in response.json()["detail"]
    assert called == []
    assert permanent_client.get("/settings").status_code == 200


@pytest.mark.parametrize(
    "payload",
    [{}, {"confirmation": "delete"}, {"confirmation": "DELETE MY ACCOUNT", "user_id": "other"}],
)
def test_confirmation_is_strict(permanent_client: TestClient, payload):
    assert permanent_client.post("/account/deletion/permanent", json=payload).status_code == 422


def test_missing_configuration_changes_nothing(permanent_client, db_session, monkeypatch):
    monkeypatch.setattr(settings, "neon_api_key", None)
    options = permanent_client.get("/account/deletion/options").json()
    assert options == {"recovery_window_days": 60, "permanent_deletion_available": False}
    assert delete_now(permanent_client).status_code == 503
    assert db_session.scalar(select(AccountDeletionRequest)) is None
    assert db_session.scalar(select(User)) is not None


def test_permanent_deletion_uses_existing_fail_closed_limit(
    permanent_client,
    db_session,
    monkeypatch,
):
    from fastapi import HTTPException

    def deny(_user_id, operation):
        assert operation == "account_deletion"
        raise HTTPException(status_code=429, detail="Try again later")

    monkeypatch.setattr("app.services.accounts.enforce_rate_limit", deny)
    assert delete_now(permanent_client).status_code == 429
    assert db_session.scalar(select(AccountDeletionRequest)) is None


def test_provider_failure_remains_pending_and_retryable(permanent_client, db_session, monkeypatch):
    def unavailable(_):
        raise RuntimeError("Do not expose provider details")

    monkeypatch.setattr("app.services.accounts.delete_neon_auth_user", unavailable)
    response = delete_now(permanent_client)
    assert response.status_code == 503
    assert "provider details" not in response.text
    pending = permanent_client.get("/account/deletion").json()
    assert pending["status"] == "pending"
    assert pending["error_message"] == "RuntimeError"
    assert permanent_client.delete("/account/deletion").status_code == 409
    assert db_session.scalar(select(User)) is not None
    monkeypatch.setattr("app.services.accounts.delete_neon_auth_user", lambda *_: None)
    assert delete_now(permanent_client).status_code == 204


def test_database_failure_after_identity_deletion_is_recoverable(
    permanent_client,
    db_session,
    monkeypatch,
):
    from app.services.accounts import purge_user_data

    def fail_purge(db, user):
        raise RuntimeError("Synthetic database outage")

    monkeypatch.setattr("app.services.accounts.purge_user_data", fail_purge)
    assert delete_now(permanent_client).status_code == 503
    request_id = db_session.scalar(select(AccountDeletionRequest.id))
    assert request_id is not None
    assert db_session.scalar(select(User)) is not None
    monkeypatch.setattr("app.services.accounts.purge_user_data", purge_user_data)
    process_account_deletion(db_session, request_id)
    process_account_deletion(db_session, request_id)
    assert db_session.scalar(select(User)) is None
