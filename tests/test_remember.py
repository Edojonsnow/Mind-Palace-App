from fastapi.testclient import TestClient


def test_remember_overview_uses_user_authored_organization(client: TestClient) -> None:
    first = client.post(
        "/thoughts",
        json={
            "body": "A private thought.",
            "manual_tags": ["Focus", "Learning"],
            "thought_type": "book_excerpt",
            "book_title": "Deep Work",
            "book_author": "Cal Newport",
        },
    ).json()
    second = client.post(
        "/thoughts",
        json={
            "body": "Another private thought.",
            "manual_tags": ["focus"],
        },
    ).json()

    response = client.get("/remember")

    assert response.status_code == 200
    assert response.json() == {
        "thoughts_analyzed": 2,
        "categories": [
            {
                "key": "tags",
                "label": "Tags",
                "items": [
                    {"label": "Focus", "count": 2},
                    {"label": "Learning", "count": 1},
                ],
            },
            {
                "key": "books",
                "label": "Books",
                "items": [{"label": "Deep Work", "count": 1}],
            },
        ],
    }
    assert first["id"] != second["id"]


def test_remember_overview_excludes_deleted_thoughts(client: TestClient) -> None:
    thought = client.post(
        "/thoughts",
        json={"body": "Temporary thought.", "manual_tags": ["temporary"]},
    ).json()
    assert client.delete(f"/thoughts/{thought['id']}").status_code == 204

    response = client.get("/remember")

    assert response.status_code == 200
    assert response.json()["thoughts_analyzed"] == 0
    assert all(not category["items"] for category in response.json()["categories"])
