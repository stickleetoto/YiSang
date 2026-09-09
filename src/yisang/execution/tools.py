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
    argument_schema: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {},
            "additionalProperties": True,
        }
    )
    side_effecting: bool = False

    def __post_init__(self) -> None:
        if not self.tool_id.strip():
            raise ValueError("tool_id must be non-empty")
        if not self.required_capabilities:
            raise ValueError("tools must require at least one E.G.O capability")
        if not isinstance(self.argument_schema, dict):
            raise ValueError("argument_schema must be a mapping")
        if self.argument_schema.get("type", "object") != "object":
            raise ValueError("argument_schema root type must be object")

    def validate_arguments(self, arguments: dict[str, Any]) -> None:
        if not isinstance(arguments, dict):
            raise ValueError("tool arguments must be an object")

        schema = self.argument_schema
        required = schema.get("required", [])
        if isinstance(required, list):
            missing = [key for key in required if key not in arguments]
            if missing:
                raise ValueError(
                    f"missing required arguments: {', '.join(map(str, missing))}"
                )

        properties = schema.get("properties", {})
        if not isinstance(properties, dict):
            properties = {}

        if schema.get("additionalProperties") is False:
            unknown = sorted(set(arguments) - set(properties))
            if unknown:
                raise ValueError(f"unknown arguments: {', '.join(unknown)}")

        for key, value in arguments.items():
            spec = properties.get(key)
            if isinstance(spec, dict):
                _validate_value_type(key, value, spec.get("type"))

    def to_context_spec(self, *, ego_id: str | None = None) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "description": self.description,
            "required_capabilities": list(self.required_capabilities),
            "required_permissions": dict(self.required_permissions),
            "argument_schema": dict(self.argument_schema),
            "side_effecting": self.side_effecting,
            "authorized_by_ego": ego_id,
        }


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


def _validate_value_type(key: str, value: Any, expected: Any) -> None:
    if expected is None:
        return

    type_map = {
        "string": str,
        "integer": int,
        "number": (int, float),
        "boolean": bool,
        "object": dict,
        "array": list,
    }
    wanted = type_map.get(expected)
    if wanted is None:
        return

    if expected in {"integer", "number"} and isinstance(value, bool):
        raise ValueError(f"argument {key} must be {expected}")
    if not isinstance(value, wanted):
        raise ValueError(f"argument {key} must be {expected}")
