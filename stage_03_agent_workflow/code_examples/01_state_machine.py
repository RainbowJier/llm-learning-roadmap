"""Deterministic state machine baseline for Agent workflow lessons."""
from dataclasses import dataclass, field
from typing import Literal

Intent = Literal["order_query", "policy_query", "chitchat"]


@dataclass
class WorkflowState:
    user_input: str
    intent: Intent | None = None
    tool_result: str = ""
    final_answer: str = ""
    retry_count: int = 0
    validation_ok: bool = False
    validation_feedback: str = ""
    trace: list[str] = field(default_factory=list)
    needs_human: bool = False


def classify(text: str) -> Intent:
    lowered = text.lower()
    if any(word in lowered for word in ("订单", "order")):
        return "order_query"
    if any(word in lowered for word in ("政策", "制度", "policy")):
        return "policy_query"
    return "chitchat"


def run_workflow(text: str, *, max_retries: int = 2) -> WorkflowState:
    state = WorkflowState(user_input=text)
    state.trace.append("classify")
    state.intent = classify(text)
    if state.intent == "order_query":
        state.trace.append("order_tool")
        state.tool_result = "订单状态：处理中"
    elif state.intent == "policy_query":
        state.trace.append("retrieval")
        state.tool_result = "政策内容：请查看最新公开制度文件"
    else:
        state.trace.append("direct_reply")
        state.tool_result = "你好，我可以帮助查询订单或政策。"

    while state.retry_count <= max_retries:
        state.trace.append("compose")
        state.final_answer = state.tool_result
        state.trace.append("validate")
        state.validation_ok = bool(state.final_answer.strip())
        if state.validation_ok:
            state.trace.append("end")
            return state
        state.retry_count += 1
        state.validation_feedback = "回答为空"
    state.trace.append("fallback")
    state.needs_human = True
    state.final_answer = "暂时无法生成可靠回答，将转人工处理。"
    return state


if __name__ == "__main__":
    print(run_workflow("我的订单到哪了"))
