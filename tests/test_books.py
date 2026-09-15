from fastapi.testclient import TestClient


def test_user_can_create_and_list_a_book(client: TestClient) -> None:
    create_response = client.post("/books", json={"title": "Circe", "author": "Madeline Miller"})

    assert create_response.status_code == 201
    book = create_response.json()
    assert book["title"] == "Circe"
    assert book["author"] == "Madeline Miller"
    assert book["thought_count"] == 0

    duplicate_response = client.post(
        "/books",
        json={"title": " circe ", "author": "MADELINE MILLER"},
    )
    assert duplicate_response.status_code == 201
    assert duplicate_response.json()["id"] == book["id"]

    list_response = client.get("/books", params={"q": "circe"})
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [book["id"]]


def test_book_excerpt_can_reference_a_saved_book(client: TestClient) -> None:
    book = client.post("/books", json={"title": "Circe", "author": "Madeline Miller"}).json()

    response = client.post(
        "/thoughts",
        json={
            "body": "A memorable excerpt.",
            "thought_type": "book_excerpt",
            "book_id": book["id"],
        },
    )

    assert response.status_code == 201
    assert response.json()["book_id"] == book["id"]
    assert response.json()["book_title"] == "Circe"
    assert response.json()["book_author"] == "Madeline Miller"
    assert client.get("/books").json()[0]["thought_count"] == 1


def test_book_excerpt_requires_book_identity(client: TestClient) -> None:
    response = client.post(
        "/thoughts",
        json={"body": "An excerpt without a book.", "thought_type": "book_excerpt"},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "Select a saved book or provide a book title and author"
