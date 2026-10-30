import importlib

preflight = importlib.import_module("stage_04_production_ready.code_examples.02_preflight")


class Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class Client:
    def __init__(self, statuses: dict[str, int]) -> None:
        self.statuses = statuses

    def get(self, path: str) -> Response:
        return Response(self.statuses[path])


def test_preflight_passes_healthy_service() -> None:
    results = preflight.run_preflight(Client({"/health": 200, "/metrics": 200}))
    assert all(result.ok for result in results)


def test_preflight_reports_failed_check() -> None:
    results = preflight.run_preflight(Client({"/health": 503, "/metrics": 200}))
    assert results[0].ok is False
    assert results[1].ok is True
