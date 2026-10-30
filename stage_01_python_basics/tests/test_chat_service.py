from fastapi.testclient import TestClient

from stage_01_python_basics.projects.chat_service.app import app

client = TestClient(app)


def test_sse_contains_ordered_events() -> None:
    response = client.post("/chat/stream", json={"query": "hello world"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    body = response.text
    assert body.index("event: status") < body.index("event: token") < body.index("event: done")


def test_websocket_chat() -> None:
    with client.websocket_connect("/ws/chat/u1") as websocket:
        assert websocket.receive_json() == {"event": "connected", "user_id": "u1"}
        websocket.send_text("hello")
        assert websocket.receive_json() == {"event": "answer", "answer": "Mock answer: hello"}
