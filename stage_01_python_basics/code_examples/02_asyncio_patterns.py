"""Small asyncio patterns with deterministic output."""
import asyncio


async def work(value: int, delay: float = 0.01) -> int:
    await asyncio.sleep(delay)
    return value * 2


async def run_concurrently(values: list[int]) -> list[int]:
    return await asyncio.gather(*(work(value) for value in values))


async def main() -> None:
    print(await run_concurrently([1, 2, 3]))


if __name__ == "__main__":
    asyncio.run(main())
