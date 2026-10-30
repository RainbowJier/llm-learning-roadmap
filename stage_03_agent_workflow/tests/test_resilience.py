import importlib

resilience = importlib.import_module("stage_03_agent_workflow.code_examples.03_retry_and_fallback")


def test_retry_then_success() -> None:
    calls = 0

    def flaky() -> str:
        nonlocal calls
        calls += 1
        if calls < 2:
            raise RuntimeError("temporary")
        return "ok"

    assert resilience.run_with_fallback(flaky, "fallback", max_retries=2) == ("ok", 1, False)


def test_fallback_after_retry_budget() -> None:
    def broken() -> str:
        raise RuntimeError("broken")

    result, attempts, degraded = resilience.run_with_fallback(broken, "safe", max_retries=2)
    assert (result, attempts, degraded) == ("safe", 3, True)
