"""Allow-listed tool calling with explicit permission and audit records."""
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ToolResult:
    name: str
    output: str
    approved: bool


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, tuple[Callable[..., str], bool]] = {}
        self.audit_log: list[dict[str, str | bool]] = []

    def register(self, name: str, function: Callable[..., str], *, write: bool = False) -> None:
        self._tools[name] = (function, write)

    def call(self, name: str, *, approved: bool = False, **kwargs: str) -> ToolResult:
        if name not in self._tools:
            raise KeyError(f"unknown tool: {name}")
        function, write = self._tools[name]
        if write and not approved:
            result = ToolResult(name, "approval required", False)
        else:
            result = ToolResult(name, function(**kwargs), True)
        self.audit_log.append({"tool": name, "approved": result.approved, "output": result.output})
        return result


def lookup_order(order_id: str) -> str:
    return f"{order_id}: processing"


if __name__ == "__main__":
    registry = ToolRegistry()
    registry.register("lookup_order", lookup_order)
    print(registry.call("lookup_order", order_id="SO-1"))
