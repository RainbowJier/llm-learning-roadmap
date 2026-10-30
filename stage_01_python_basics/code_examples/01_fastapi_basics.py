"""Minimal FastAPI example.

Run from the repository root:
    uvicorn stage_01_python_basics.code_examples.01_fastapi_basics:app --reload
"""
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="Stage 1 FastAPI Basics")


class GreetingRequest(BaseModel):
    name: str = Field(min_length=1, max_length=50)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/greet")
async def greet(request: GreetingRequest) -> dict[str, str]:
    return {"message": f"Hello, {request.name}!"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)
