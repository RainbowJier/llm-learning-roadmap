import asyncio
import importlib

patterns = importlib.import_module(
    "stage_01_python_basics.code_examples.02_asyncio_patterns"
)


def test_run_concurrently() -> None:
    assert asyncio.run(patterns.run_concurrently([1, 2, 3])) == [2, 4, 6]
