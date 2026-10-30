"""Offline preflight checks for a service URL."""
from dataclasses import dataclass
from typing import Protocol


class HttpClient(Protocol):
    def get(self, path: str) -> object: ...


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def run_preflight(client: HttpClient) -> list[CheckResult]:
    results: list[CheckResult] = []
    for name, path in (("health", "/health"), ("metrics", "/metrics")):
        try:
            response = client.get(path)
            status = getattr(response, "status_code", 0)
            results.append(CheckResult(name, status == 200, f"status={status}"))
        except Exception as exc:
            results.append(CheckResult(name, False, str(exc)))
    return results


if __name__ == "__main__":
    print("Pass an HTTP client from a test or deployment script.")
