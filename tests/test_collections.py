from fastapi.testclient import TestClient
from sqlalchemy import select

from app.models import Collection, Thought, User
from app.services.accounts import purge_user_data


def test_user_can_create_and_list_collections(client: TestClient) -> None:
    first_response = client.post("/collections", json={"name": "Career ideas"})
    assert first_response.status_code == 201
    first = first_response.json()
    assert first["name"] == "Career ideas"
    assert first["thought_count"] == 0

    duplicate_response = client.post("/collections", json={"name": " career   IDEAS "})
    assert duplicate_response.status_code == 409

    second_response = client.post("/collections", json={"name": "Reading list"})
    assert second_response.status_code == 201

    response = client.get("/collections")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["Career ideas", "Reading list"]


def test_collection_membership_is_many_to_many_and_deletion_preserves_thoughts(
    client: TestClient,
) -> None:
    collection = client.post("/collections", json={"name": "Projects"}).json()
    first = client.post("/thoughts", json={"body": "First project thought."}).json()
    second = client.post("/thoughts", json={"body": "Second project thought."}).json()

    add_first = client.post(f"/collections/{collection['id']}/thoughts/{first['id']}")
    add_second = client.post(f"/collections/{collection['id']}/thoughts/{second['id']}")
    assert add_first.status_code == 200
    assert add_second.status_code == 200
    assert add_second.json()["thought_count"] == 2

    collection_thoughts = client.get(f"/collections/{collection['id']}/thoughts")
    assert collection_thoughts.status_code == 200
    assert {item["id"] for item in collection_thoughts.json()} == {first["id"], second["id"]}

    filtered = client.get("/thoughts", params={"collection_id": collection["id"]})
    assert filtered.status_code == 200
    assert {item["id"] for item in filtered.json()} == {first["id"], second["id"]}

    assert client.delete(f"/collections/{collection['id']}").status_code == 204
    assert client.get(f"/thoughts/{first['id']}").status_code == 200
    assert client.get(f"/thoughts/{second['id']}").status_code == 200


def test_deleted_thoughts_do_not_count_in_collections(client: TestClient) -> None:
    collection = client.post("/collections", json={"name": "Archive"}).json()
    thought = client.post("/thoughts", json={"body": "A thought to archive."}).json()
    client.post(f"/collections/{collection['id']}/thoughts/{thought['id']}")

    assert client.delete(f"/thoughts/{thought['id']}").status_code == 204
    response = client.get("/collections")

    assert response.status_code == 200
    assert response.json()[0]["thought_count"] == 0
    assert client.get(f"/collections/{collection['id']}/thoughts").json() == []


def test_account_purge_removes_collections_and_memberships(client: TestClient, db_session) -> None:
    collection = client.post("/collections", json={"name": "Private"}).json()
    thought = client.post("/thoughts", json={"body": "Private thought."}).json()
    client.post(f"/collections/{collection['id']}/thoughts/{thought['id']}")

    user = db_session.scalar(select(User).where(User.auth_user_id == "test-auth-user"))
    assert user is not None
    purge_user_data(db_session, user)

    assert db_session.scalars(select(Collection)).all() == []
    assert db_session.scalars(select(Thought)).all() == []
