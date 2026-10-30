from fastapi.testclient import TestClient

from stage_01_python_basics.projects.chat_service.app import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_chat_validates_and_answers() -> None:
    response = client.post("/chat", json={"query": "hello"})
    assert response.status_code == 200
    assert response.json()["answer"] == "Mock answer: hello"


def test_chat_rejects_empty_query() -> None:
    response = client.post("/chat", json={"query": ""})
    assert response.status_code == 422
