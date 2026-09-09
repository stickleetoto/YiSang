from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from yisang.execution.models import ActionProposal


@dataclass(frozen=True)
class DecodedEngineMessage:
    text: str
    actions: list[ActionProposal]


class StructuredActionDecoder:
    def __init__(self, *, max_actions: int = 8, max_argument_chars: int = 8_000) -> None:
        if max_actions <= 0 or max_argument_chars <= 0:
            raise ValueError("decoder limits must be positive")
        self.max_actions = max_actions
        self.max_argument_chars = max_argument_chars

    def decode(self, message: dict[str, Any], *, requested_by: str) -> DecodedEngineMessage:
        if not isinstance(message, dict):
            raise ValueError("engine message must be an object")

        content = message.get("content")
        if content is None:
            content = ""
        if not isinstance(content, str):
            raise ValueError("response content must be a string or null")

        native_calls = message.get("tool_calls")
        if native_calls is not None:
            actions = self._decode_native_tool_calls(native_calls, requested_by=requested_by)
            return DecodedEngineMessage(content, actions)

        envelope = _try_json_envelope(content)
        if envelope is None:
            return DecodedEngineMessage(content, [])

        response = envelope.get("response", "")
        if not isinstance(response, str):
            raise ValueError("structured response field must be a string")

        actions = self._decode_action_list(
            envelope.get("actions", []),
            requested_by=requested_by,
        )
        return DecodedEngineMessage(response, actions)

    def _decode_native_tool_calls(
        self,
        raw: Any,
        *,
        requested_by: str,
    ) -> list[ActionProposal]:
        if not isinstance(raw, list):
            raise ValueError("tool_calls must be a list")
        if len(raw) > self.max_actions:
            raise ValueError("too many tool calls")

        actions: list[ActionProposal] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("tool call must be an object")
            function = item.get("function")
            if not isinstance(function, dict):
                raise ValueError("tool call function must be an object")
            name = function.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("tool call function name is required")
            arguments = _decode_arguments(
                function.get("arguments", {}),
                self.max_argument_chars,
            )
            actions.append(
                ActionProposal(
                    name.strip(),
                    arguments,
                    requested_by=requested_by,
                )
            )
        return actions

    def _decode_action_list(
        self,
        raw: Any,
        *,
        requested_by: str,
    ) -> list[ActionProposal]:
        if not isinstance(raw, list):
            raise ValueError("actions must be a list")
        if len(raw) > self.max_actions:
            raise ValueError("too many actions")

        actions: list[ActionProposal] = []
        for item in raw:
            if not isinstance(item, dict):
                raise ValueError("action entry must be an object")
            tool = item.get("tool", item.get("action"))
            if not isinstance(tool, str) or not tool.strip():
                raise ValueError("action tool id is required")
            arguments = _decode_arguments(
                item.get("arguments", {}),
                self.max_argument_chars,
            )
            actions.append(
                ActionProposal(
                    tool.strip(),
                    arguments,
                    requested_by=requested_by,
                )
            )
        return actions


def _decode_arguments(raw: Any, max_chars: int) -> dict[str, Any]:
    if isinstance(raw, str):
        if len(raw) > max_chars:
            raise ValueError("tool arguments exceed size limit")
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("tool arguments must be valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("tool arguments must be an object")

    serialized = json.dumps(raw, ensure_ascii=False, separators=(",", ":"))
    if len(serialized) > max_chars:
        raise ValueError("tool arguments exceed size limit")
    return raw


def _try_json_envelope(content: str) -> dict[str, Any] | None:
    candidate = content.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()

    if not candidate.startswith("{"):
        return None

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None

    if not isinstance(parsed, dict) or "actions" not in parsed:
        return None
    return parsed
