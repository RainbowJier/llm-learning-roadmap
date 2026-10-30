import importlib

workflow = importlib.import_module("stage_03_agent_workflow.code_examples.01_state_machine")


def test_order_path_has_bounded_trace() -> None:
    state = workflow.run_workflow("订单 SO-1 到哪了")
    assert state.intent == "order_query"
    assert state.validation_ok is True
    assert state.needs_human is False
    assert state.trace[-1] == "end"


def test_unknown_input_is_safe_chitchat() -> None:
    state = workflow.run_workflow("你好")
    assert state.intent == "chitchat"
    assert "direct_reply" in state.trace
