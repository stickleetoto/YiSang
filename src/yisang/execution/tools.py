from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

ToolHandler = Callable[[dict[str, Any]], Any]


@dataclass(frozen=True)
class ToolDefinition:
    tool_id: str
    handler: ToolHandler
    description: str = ""
    required_capabilities: tuple[str, ...] = ()
    required_permissions: dict[str, str | bool] = field(default_factory=dict)
    side_effecting: bool = False

    def __post_init__(self) -> None:
        if not self.tool_id.strip():
            raise ValueError("tool_id must be non-empty")
        if not self.required_capabilities:
            raise ValueError("tools must require at least one E.G.O capability")


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.tool_id in self._tools:
            raise ValueError(f"duplicate tool id: {tool.tool_id}")
        self._tools[tool.tool_id] = tool

    def get(self, tool_id: str) -> ToolDefinition:
        try:
            return self._tools[tool_id]
        except KeyError as exc:
            raise KeyError(f"tool not registered: {tool_id}") from exc

    def has(self, tool_id: str) -> bool:
        return tool_id in self._tools

    def list_all(self) -> list[ToolDefinition]:
        return list(self._tools.values())
