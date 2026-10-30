"""Bounded retry and fallback helpers."""
from collections.abc import Callable


def run_with_fallback(operation: Callable[[], str], fallback: str, max_retries: int = 2) -> tuple[str, int, bool]:
    attempts = 0
    while attempts <= max_retries:
        try:
            return operation(), attempts, False
        except Exception:
            attempts += 1
    return fallback, attempts, True


if __name__ == "__main__":
    print(run_with_fallback(lambda: "ok", "fallback"))
