import importlib

registry_module = importlib.import_module("stage_03_agent_workflow.code_examples.02_tool_calling")


def test_read_tool_is_allowlisted_and_audited() -> None:
    registry = registry_module.ToolRegistry()
    registry.register("lookup_order", registry_module.lookup_order)
    result = registry.call("lookup_order", order_id="SO-1")
    assert result.approved is True
    assert result.output == "SO-1: processing"
    assert registry.audit_log[-1]["tool"] == "lookup_order"


def test_write_tool_requires_approval() -> None:
    registry = registry_module.ToolRegistry()
    registry.register("cancel_order", lambda order_id: f"cancelled {order_id}", write=True)
    result = registry.call("cancel_order", order_id="SO-1")
    assert result.approved is False
    assert result.output == "approval required"
