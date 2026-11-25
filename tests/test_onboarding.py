import importlib.util
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app import models
from app.core.auth import AuthenticatedUser, get_current_user
from app.services.export_payload import build_export_payload


def test_new_account_starts_with_private_defaults(client: TestClient):
    settings = client.get("/settings").json()
    assert settings["onboarding_step"] == "privacy"
    assert settings["onboarding_completed_at"] is None
    assert settings["default_use_with_ask_my_mind"] is False


def test_progress_resumes_and_completion_cannot_be_reopened(client: TestClient):
    continued = client.patch("/settings/onboarding", json={"action": "continue"})
    assert continued.status_code == 200
    assert continued.json()["onboarding_step"] == "first_thought"
    assert client.get("/settings").json()["onboarding_step"] == "first_thought"
    assert client.get("/settings").json()["onboarding_completed_at"] is None

    completed_at = client.patch("/settings/onboarding", json={"action": "skip"}).json()[
        "onboarding_completed_at"
    ]
    assert completed_at is not None
    for action in ["skip", "continue"]:
        response = client.patch("/settings/onboarding", json={"action": action})
        assert response.json()["onboarding_completed_at"] == completed_at
        assert response.json()["default_use_with_ask_my_mind"] is False


def test_successful_capture_completes_onboarding_without_ai(
    client: TestClient, db_session: Session,
):
    client.patch("/settings/onboarding", json={"action": "continue"})
    saved = client.post("/thoughts", json={"body": "A synthetic first thought."})
    assert saved.status_code == 201
    assert saved.json()["use_with_ask_my_mind"] is False
    assert client.get("/settings").json()["onboarding_completed_at"] is not None
    assert db_session.scalar(select(models.BackgroundJob)) is None
    assert db_session.scalar(select(models.ThoughtChunk)) is None
    assert db_session.scalar(select(models.ThoughtMetadata)) is None
    assert db_session.scalar(select(models.AIPreferences)) is None
    user = db_session.scalar(select(models.User))
    assert build_export_payload(db_session, user)["settings"]["onboarding_completed_at"]


def test_failed_capture_keeps_onboarding_incomplete(client: TestClient):
    client.patch("/settings/onboarding", json={"action": "continue"})
    response = client.post("/thoughts", json={"body": "An invalid excerpt.",
                                             "thought_type": "book_excerpt"})
    assert response.status_code == 400
    assert client.get("/settings").json()["onboarding_completed_at"] is None


def test_skip_preserves_existing_ai_preferences(client: TestClient):
    client.patch("/settings", json={"default_use_with_ask_my_mind": True})
    response = client.patch("/settings/onboarding", json={"action": "skip"})
    assert response.json()["default_use_with_ask_my_mind"] is True


def test_capture_replay_does_not_repeat_completion(client: TestClient):
    headers = {"Idempotency-Key": "onboarding-first-capture"}
    payload = {"body": "A synthetic idempotent first thought."}
    first = client.post("/thoughts", json=payload, headers=headers)
    assert first.status_code == 201
    completed_at = client.get("/settings").json()["onboarding_completed_at"]
    replay = client.post("/thoughts", json=payload, headers=headers)
    assert replay.json()["id"] == first.json()["id"]
    assert client.get("/settings").json()["onboarding_completed_at"] == completed_at


def test_rate_limited_setup_does_not_change_progress(client: TestClient, monkeypatch):
    from fastapi import HTTPException

    def reject(user_id, bucket):
        assert bucket == "settings_write"
        raise HTTPException(429, "Try again later", headers={"Retry-After": "30"})

    client.get("/settings")
    monkeypatch.setattr("app.services.settings.enforce_rate_limit", reject)
    response = client.patch("/settings/onboarding", json={"action": "skip"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "30"
    assert client.get("/settings").json()["onboarding_completed_at"] is None


def test_onboarding_is_scoped_to_authenticated_user(client: TestClient):
    client.patch("/settings/onboarding", json={"action": "skip"})

    async def other_user():
        return AuthenticatedUser(auth_user_id="another-user", email="another@example.test")

    client.app.dependency_overrides[get_current_user] = other_user
    try:
        response = client.get("/settings")
        assert response.json()["onboarding_completed_at"] is None
        assert response.json()["onboarding_step"] == "privacy"
    finally:
        client.app.dependency_overrides.pop(get_current_user)


@pytest.mark.parametrize("payload", [
    {}, {"action": "reset"}, {"action": "skip", "default_use_with_ask_my_mind": True},
])
def test_onboarding_rejects_invalid_actions_and_consent_changes(client: TestClient, payload):
    assert client.patch("/settings/onboarding", json=payload).status_code == 422


def test_migration_exempts_existing_accounts_but_not_new_accounts():
    path = Path("migrations/versions/20261121_0015_add_onboarding_progress.py")
    spec = importlib.util.spec_from_file_location("onboarding_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE user_settings (id INTEGER PRIMARY KEY)"))
        connection.execute(text("INSERT INTO user_settings (id) VALUES (1)"))
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            migration.upgrade()
            connection.execute(text("INSERT INTO user_settings (id) VALUES (2)"))
            rows = connection.execute(text("SELECT * FROM user_settings ORDER BY id")).mappings()
            existing, new = list(rows)
            assert existing["onboarding_completed_at"] is not None
            assert new["onboarding_completed_at"] is None
            assert new["onboarding_step"] == "privacy"
            migration.downgrade()
