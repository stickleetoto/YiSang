from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProtocolError(Exception):
    message: str
    code: str = "invalid_request"
    param: str | None = None
    status: int = 400

    def __str__(self) -> str:
        return self.message


def require_model(payload: dict[str, Any], model_id: str) -> None:
    requested = payload.get("model")
    if not isinstance(requested, str) or not requested.strip():
        raise ProtocolError("model is required", param="model")
    if requested != model_id:
        raise ProtocolError(
            f"model not found: {requested}",
            code="model_not_found",
            param="model",
            status=404,
        )


def parse_chat_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    raw = payload.get("messages")
    if not isinstance(raw, list) or not raw:
        raise ProtocolError("messages must be a non-empty list", param="messages")

    messages: list[dict[str, str]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ProtocolError("message must be an object", param=f"messages[{index}]")
        role = item.get("role")
        if role not in {"system", "developer", "user", "assistant", "tool"}:
            raise ProtocolError("unsupported message role", param=f"messages[{index}].role")
        content = _content_to_text(item.get("content"))
        if role == "tool" and item.get("tool_call_id"):
            content = f"tool_call_id={item['tool_call_id']}\n{content}"
        messages.append({"role": role, "content": content})
    return messages


def parse_responses_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    instructions = payload.get("instructions")
    if instructions is not None:
        messages.append({"role": "developer", "content": _content_to_text(instructions)})

    raw = payload.get("input")
    if isinstance(raw, str):
        messages.append({"role": "user", "content": raw})
        return messages
    if not isinstance(raw, list) or not raw:
        raise ProtocolError("input must be text or a non-empty list", param="input")

    for index, item in enumerate(raw):
        if isinstance(item, str):
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            raise ProtocolError("input item must be an object", param=f"input[{index}]")

        item_type = item.get("type")
        role = item.get("role")
        if item_type in {"function_call_output", "custom_tool_call_output"}:
            call_id = item.get("call_id", "unknown")
            output = _content_to_text(item.get("output"))
            messages.append({"role": "tool", "content": f"call_id={call_id}\n{output}"})
            continue
        if item_type in {"function_call", "custom_tool_call"}:
            name = item.get("name", "unknown")
            arguments = item.get("arguments", "{}")
            messages.append({
                "role": "assistant",
                "content": f"tool_call name={name} arguments={arguments}",
            })
            continue
        if role in {"system", "developer", "user", "assistant", "tool"}:
            messages.append({"role": role, "content": _content_to_text(item.get("content"))})
            continue
        raise ProtocolError("unsupported input item", param=f"input[{index}]")

    return messages


def normalize_tools(payload: dict[str, Any], *, responses: bool = False) -> list[dict[str, Any]]:
    raw = payload.get("tools", [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ProtocolError("tools must be a list", param="tools")

    tools: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            raise ProtocolError("tool must be an object", param=f"tools[{index}]")
        if item.get("type") != "function":
            # YiSang model-server v0.1 delegates client-owned function tools only.
            continue

        function = item if responses else item.get("function")
        if not isinstance(function, dict):
            raise ProtocolError("function tool definition is required", param=f"tools[{index}]")
        name = function.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ProtocolError("function tool name is required", param=f"tools[{index}].name")
        parameters = function.get("parameters", {})
        if not isinstance(parameters, dict):
            raise ProtocolError("function parameters must be an object", param=f"tools[{index}].parameters")

        tools.append({
            "tool_id": name.strip(),
            "description": str(function.get("description", "")),
            "argument_schema": parameters,
            "delegated": True,
        })
    return tools


def render_messages(messages: list[dict[str, str]]) -> str:
    return "\n\n".join(
        f"[{item['role'].upper()}]\n{item['content']}" for item in messages
    )


def last_user_text(messages: list[dict[str, str]]) -> str:
    for item in reversed(messages):
        if item["role"] == "user" and item["content"].strip():
            return item["content"]
    return messages[-1]["content"] if messages else ""


def error_payload(error: ProtocolError) -> dict[str, Any]:
    return {
        "error": {
            "message": error.message,
            "type": "invalid_request_error",
            "param": error.param,
            "code": error.code,
        }
    }


def _content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
                elif item.get("type") in {"input_text", "output_text", "text"}:
                    parts.append(str(item.get("text", "")))
        return "\n".join(parts)
    if isinstance(value, (dict, int, float, bool)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)
