"""Framework-free SSE event generator."""
import asyncio
from collections.abc import AsyncIterator


async def stream_tokens(text: str) -> AsyncIterator[str]:
    for token in text.split():
        await asyncio.sleep(0)
        yield f"event: token\ndata: {token}\n\n"
    yield "event: done\ndata: {}\n\n"


async def main() -> None:
    async for event in stream_tokens("hello async world"):
        print(event, end="")


if __name__ == "__main__":
    asyncio.run(main())
