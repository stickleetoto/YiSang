from __future__ import annotations

from dataclasses import dataclass
import json
import time
from typing import Any
from uuid import uuid4

from .proxy import PreparedChatRequest, YiSangModelProxy


@dataclass(frozen=True)
class PreparedResponsesRequest:
    request_id: str
    chat_payload: dict[str, Any]
    stream: bool
    tool_metadata: dict[str, tuple[str, str | None, str]]


def prepare_responses_request(
    proxy: YiSangModelProxy,
    payload: dict[str, Any],
) -> PreparedResponsesRequest:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if model != proxy.model_id:
        raise ValueError(f"unknown YiSang model: {model}")

    messages = _responses_input_to_chat_messages(payload)
    if not messages:
        raise ValueError("input must contain at least one message or tool result")

    tools, tool_metadata = _responses_tools_to_chat(payload.get("tools"))
    chat_payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        # Codex uses Responses streaming, but YiSang deliberately completes the
        # local Chat request first and then emits canonical Responses SSE events.
        "stream": False,
    }
    if tools:
        chat_payload["tools"] = tools

    tool_choice = _tool_choice_to_chat(payload.get("tool_choice"), tool_metadata)
    if tool_choice is not None:
        chat_payload["tool_choice"] = tool_choice

    if isinstance(payload.get("parallel_tool_calls"), bool):
        chat_payload["parallel_tool_calls"] = payload["parallel_tool_calls"]
    if isinstance(payload.get("temperature"), (int, float)):
        chat_payload["temperature"] = payload["temperature"]
    if isinstance(payload.get("top_p"), (int, float)):
        chat_payload["top_p"] = payload["top_p"]
    if isinstance(payload.get("max_output_tokens"), int):
        chat_payload["max_tokens"] = payload["max_output_tokens"]

    prepared: PreparedChatRequest = proxy.prepare_chat_request(chat_payload)
    return PreparedResponsesRequest(
        request_id=prepared.request_id,
        chat_payload=prepared.payload,
        stream=bool(payload.get("stream", False)),
        tool_metadata=tool_metadata,
    )


def chat_response_to_responses(
    *,
    proxy: YiSangModelProxy,
    chat_response: dict[str, Any],
    tool_metadata: dict[str, tuple[str, str | None, str]],
) -> dict[str, Any]:
    if not isinstance(chat_response, dict):
        raise ValueError("upstream response must be a JSON object")

    response_id = f"resp_{uuid4().hex}"
    items = _chat_response_items(chat_response, tool_metadata)
    usage = _responses_usage(chat_response.get("usage"))

    return {
        "id": response_id,
        "object": "response",
        "created_at": int(time.time()),
        "status": "completed",
        "model": proxy.model_id,
        "output": items,
        "usage": usage,
        "error": None,
        "incomplete_details": None,
    }


def responses_sse_events(response: dict[str, Any]) -> list[bytes]:
    response_id = str(response["id"])
    created = {
        "type": "response.created",
        "response": {
            "id": response_id,
            "model": response.get("model"),
            "status": "in_progress",
        },
    }

    events: list[dict[str, Any]] = [created]
    for item in response.get("output", []):
        events.append({
            "type": "response.output_item.done",
            "item": item,
        })

    events.append({
        "type": "response.completed",
        "response": {
            "id": response_id,
            "model": response.get("model"),
            "status": "completed",
            "usage": response.get("usage"),
        },
    })
    return [_encode_sse_event(event) for event in events]


def _encode_sse_event(event: dict[str, Any]) -> bytes:
    kind = str(event["type"])
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"event: {kind}\ndata: {data}\n\n".encode("utf-8")


def _responses_input_to_chat_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        messages.append({"role": "user", "content": raw_input})
        return messages
    if not isinstance(raw_input, list):
        raise ValueError("input must be a string or list")

    pending_tool_calls: list[dict[str, Any]] = []

    def flush_tool_calls() -> None:
        if pending_tool_calls:
            messages.append({
                "role": "assistant",
                "content": None,
                "tool_calls": list(pending_tool_calls),
            })
            pending_tool_calls.clear()

    for item in raw_input:
        if isinstance(item, str):
            flush_tool_calls()
            messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        if item_type in {"function_call", "custom_tool_call"}:
            call_id = str(item.get("call_id") or item.get("id") or f"call_{uuid4().hex}")
            namespace = item.get("namespace")
            name = str(item.get("name") or "tool")
            wire_name = _wire_tool_name(
                str(namespace) if isinstance(namespace, str) else None,
                name,
            )
            arguments = item.get("arguments")
            if item_type == "custom_tool_call":
                raw_input_value = item.get("input", "")
                arguments = json.dumps({"input": raw_input_value}, ensure_ascii=False)
            elif not isinstance(arguments, str):
                arguments = json.dumps(arguments or {}, ensure_ascii=False)
            pending_tool_calls.append({
                "id": call_id,
                "type": "function",
                "function": {
                    "name": wire_name,
                    "arguments": arguments,
                },
            })
            continue

        flush_tool_calls()

        if item_type in {"function_call_output", "custom_tool_call_output"}:
            messages.append({
                "role": "tool",
                "tool_call_id": str(item.get("call_id") or ""),
                "content": _output_to_text(item.get("output")),
            })
            continue

        if item_type == "message" or item.get("role") is not None:
            role = str(item.get("role") or "user")
            if role == "developer":
                role = "system"
            if role not in {"system", "user", "assistant", "tool"}:
                role = "user"
            message: dict[str, Any] = {
                "role": role,
                "content": _content_to_text(item.get("content")),
            }
            if role == "tool" and item.get("call_id"):
                message["tool_call_id"] = str(item["call_id"])
            messages.append(message)

    flush_tool_calls()
    return messages


def _responses_tools_to_chat(
    raw_tools: Any,
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str | None, str]]]:
    if raw_tools is None:
        return [], {}
    if not isinstance(raw_tools, list):
        raise ValueError("tools must be a list")

    tools: list[dict[str, Any]] = []
    metadata: dict[str, tuple[str, str | None, str]] = {}

    def add_function(
        *,
        name: str,
        description: str,
        parameters: Any,
        kind: str = "function",
        namespace: str | None = None,
        original_name: str | None = None,
    ) -> None:
        wire_name = _wire_tool_name(namespace, name)
        schema = parameters if isinstance(parameters, dict) else {"type": "object"}
        tools.append({
            "type": "function",
            "function": {
                "name": wire_name,
                "description": description,
                "parameters": schema,
            },
        })
        metadata[wire_name] = (kind, namespace, original_name or name)

    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type")

        if tool_type == "function":
            name = tool.get("name")
            if isinstance(name, str) and name:
                add_function(
                    name=name,
                    description=str(tool.get("description") or ""),
                    parameters=tool.get("parameters", {"type": "object"}),
                )
            continue

        if tool_type == "namespace":
            namespace = tool.get("name")
            children = tool.get("tools")
            if not isinstance(namespace, str) or not isinstance(children, list):
                continue
            for child in children:
                if not isinstance(child, dict) or child.get("type") != "function":
                    continue
                child_name = child.get("name")
                if not isinstance(child_name, str) or not child_name:
                    continue
                add_function(
                    name=child_name,
                    description=str(child.get("description") or ""),
                    parameters=child.get("parameters", {"type": "object"}),
                    namespace=namespace,
                    original_name=child_name,
                )
            continue

        if tool_type == "custom":
            name = tool.get("name")
            if isinstance(name, str) and name:
                add_function(
                    name=name,
                    description=str(tool.get("description") or ""),
                    parameters={
                        "type": "object",
                        "properties": {"input": {"type": "string"}},
                        "required": ["input"],
                    },
                    kind="custom",
                )

    return tools, metadata


def _tool_choice_to_chat(
    value: Any,
    metadata: dict[str, tuple[str, str | None, str]],
) -> Any:
    if value in {"auto", "none", "required"}:
        return value
    if not isinstance(value, dict):
        return None

    if value.get("type") == "function":
        name = value.get("name")
        if isinstance(name, str):
            return {"type": "function", "function": {"name": name}}

    return None


def _chat_response_items(
    chat_response: dict[str, Any],
    tool_metadata: dict[str, tuple[str, str | None, str]],
) -> list[dict[str, Any]]:
    choices = chat_response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("upstream chat response is missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("upstream chat response is missing assistant message")

    items: list[dict[str, Any]] = []
    content = message.get("content")
    if isinstance(content, str) and content:
        items.append({
            "type": "message",
            "role": "assistant",
            "id": f"msg_{uuid4().hex}",
            "content": [{"type": "output_text", "text": content}],
        })

    tool_calls = message.get("tool_calls")
    if isinstance(tool_calls, list):
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            function = call.get("function")
            if not isinstance(function, dict):
                continue
            wire_name = function.get("name")
            if not isinstance(wire_name, str) or not wire_name:
                continue
            call_id = str(call.get("id") or f"call_{uuid4().hex}")
            arguments = function.get("arguments", "{}")
            if not isinstance(arguments, str):
                arguments = json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))

            kind, namespace, original_name = tool_metadata.get(
                wire_name,
                ("function", None, wire_name),
            )
            if kind == "custom":
                custom_input = arguments
                try:
                    decoded = json.loads(arguments)
                    if isinstance(decoded, dict) and isinstance(decoded.get("input"), str):
                        custom_input = decoded["input"]
                except json.JSONDecodeError:
                    pass
                items.append({
                    "type": "custom_tool_call",
                    "call_id": call_id,
                    "name": original_name,
                    "input": custom_input,
                })
            else:
                item: dict[str, Any] = {
                    "type": "function_call",
                    "call_id": call_id,
                    "name": original_name,
                    "arguments": arguments,
                }
                if namespace:
                    item["namespace"] = namespace
                items.append(item)

    return items


def _responses_usage(raw_usage: Any) -> dict[str, Any]:
    usage = raw_usage if isinstance(raw_usage, dict) else {}
    input_tokens = int(usage.get("prompt_tokens", usage.get("input_tokens", 0)) or 0)
    output_tokens = int(
        usage.get("completion_tokens", usage.get("output_tokens", 0)) or 0
    )
    total_tokens = int(usage.get("total_tokens", input_tokens + output_tokens) or 0)
    return {
        "input_tokens": input_tokens,
        "input_tokens_details": {
            "cached_tokens": int(
                (usage.get("prompt_tokens_details") or {}).get("cached_tokens", 0)
                if isinstance(usage.get("prompt_tokens_details"), dict)
                else 0
            )
        },
        "output_tokens": output_tokens,
        "output_tokens_details": {"reasoning_tokens": 0},
        "total_tokens": total_tokens,
    }


def _wire_tool_name(namespace: str | None, name: str) -> str:
    if namespace:
        return f"{namespace}__{name}"
    return name


def _content_to_text(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return json.dumps(content, ensure_ascii=False)

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "\n".join(parts)


def _output_to_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return _content_to_text(output)
    if isinstance(output, dict):
        content = output.get("content")
        if isinstance(content, str):
            return content
    return json.dumps(output, ensure_ascii=False)
