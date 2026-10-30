"""Offline chat service used by the Stage 1 exercises.

It deliberately uses an in-memory store and a deterministic mock backend so
learners can run the API without a database or an LLM provider.
"""
import asyncio
from collections import deque
from collections.abc import AsyncIterator
from time import monotonic

from fastapi import FastAPI, WebSocket
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

app = FastAPI(title="Stage 1 Chat Service")


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


class ChatResponse(BaseModel):
    answer: str
    backend: str = "mock"


class Metrics:
    def __init__(self, max_samples: int = 1000) -> None:
        self.latencies: deque[float] = deque(maxlen=max_samples)
        self.requests = 0
        self.errors = 0

    def record(self, elapsed_ms: float, error: bool = False) -> None:
        self.latencies.append(elapsed_ms)
        self.requests += 1
        self.errors += int(error)


metrics = Metrics()
concurrency_limit = asyncio.Semaphore(20)


def mock_answer(query: str) -> str:
    return f"Mock answer: {query.strip()}"


async def stream_answer(query: str) -> AsyncIterator[str]:
    answer = mock_answer(query)
    yield "event: status\ndata: started\n\n"
    for token in answer.split():
        await asyncio.sleep(0)
        yield f"event: token\ndata: {token}\n\n"
    yield "event: done\ndata: complete\n\n"


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "backend": "mock"}


@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    started = monotonic()
    async with concurrency_limit:
        try:
            await asyncio.sleep(0)
            response = ChatResponse(answer=mock_answer(request.query))
            metrics.record((monotonic() - started) * 1000)
            return response
        except Exception:
            metrics.record((monotonic() - started) * 1000, error=True)
            raise


@app.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    return StreamingResponse(
        stream_answer(request.query),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/admin/stats")
async def stats() -> dict[str, float | int]:
    samples = sorted(metrics.latencies)
    p95_index = max(0, int(len(samples) * 0.95) - 1)
    return {
        "requests": metrics.requests,
        "errors": metrics.errors,
        "p95_ms": samples[p95_index] if samples else 0.0,
    }


@app.websocket("/ws/chat/{user_id}")
async def websocket_chat(websocket: WebSocket, user_id: str) -> None:
    await websocket.accept()
    await websocket.send_json({"event": "connected", "user_id": user_id})
    try:
        while True:
            query = await websocket.receive_text()
            await websocket.send_json({"event": "answer", "answer": mock_answer(query)})
    except Exception:
        await websocket.close()
