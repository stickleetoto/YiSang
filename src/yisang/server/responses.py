from __future__ import annotations

from dataclasses import dataclass
import ast
import json
import time
from typing import Any
from uuid import uuid4

from .proxy import PreparedChatRequest, YiSangModelProxy

_CODEX_SMALL_ALLOWED_TOOLS = frozenset({"exec_command", "apply_patch"})
_CODEX_SMALL_SYSTEM_MESSAGE = (
    "[YISANG CODEX SMALL-MODEL TOOL PROFILE]\n"
    "Only tools present in the attached tools array are executable. Ignore tool "
    "names mentioned elsewhere when they are not present. For local file and "
    "shell work, prefer exec_command. Never print a tool call as JSON in normal "
    "assistant text; issue a structured tool call instead.\n"
    "[END YISANG CODEX SMALL-MODEL TOOL PROFILE]"
)


@dataclass(frozen=True)
class PreparedResponsesRequest:
    request_id: str
    chat_payload: dict[str, Any]
    stream: bool
    tool_metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]]


def prepare_responses_request(
    proxy: YiSangModelProxy,
    payload: dict[str, Any],
    *,
    tool_profile: str = "full",
) -> PreparedResponsesRequest:
    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if model != proxy.model_id:
        raise ValueError(f"unknown YiSang model: {model}")

    if tool_profile not in {"full", "codex-small"}:
        raise ValueError(f"unknown tool profile: {tool_profile}")

    messages = _responses_input_to_chat_messages(payload)
    if not messages:
        raise ValueError("input must contain at least one message or tool result")
    if tool_profile == "codex-small":
        insert_at = 1 if messages and messages[0].get("role") == "system" else 0
        messages.insert(
            insert_at,
            {"role": "system", "content": _CODEX_SMALL_SYSTEM_MESSAGE},
        )

    tools, tool_metadata = _responses_tools_to_chat(
        payload.get("tools"),
        tool_profile=tool_profile,
    )
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

    if tool_profile == "codex-small":
        chat_payload["parallel_tool_calls"] = False
    elif isinstance(payload.get("parallel_tool_calls"), bool):
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
    tool_metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]],
    recover_text_tool_calls: bool = False,
) -> dict[str, Any]:
    if not isinstance(chat_response, dict):
        raise ValueError("upstream response must be a JSON object")

    response_id = f"resp_{uuid4().hex}"
    items = _chat_response_items(
        chat_response,
        tool_metadata,
        recover_text_tool_calls=recover_text_tool_calls,
    )
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
    *,
    tool_profile: str = "full",
) -> tuple[list[dict[str, Any]], dict[str, tuple[str, str | None, str, dict[str, Any]]]]:
    if raw_tools is None:
        return [], {}
    if not isinstance(raw_tools, list):
        raise ValueError("tools must be a list")

    tools: list[dict[str, Any]] = []
    metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]] = {}

    def add_function(
        *,
        name: str,
        description: str,
        parameters: Any,
        kind: str = "function",
        namespace: str | None = None,
        original_name: str | None = None,
    ) -> None:
        if tool_profile == "codex-small" and name not in _CODEX_SMALL_ALLOWED_TOOLS:
            return
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
        metadata[wire_name] = (kind, namespace, original_name or name, schema)

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
    metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]],
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
    tool_metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]],
    *,
    recover_text_tool_calls: bool = False,
) -> list[dict[str, Any]]:
    choices = chat_response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("upstream chat response is missing choices")

    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise ValueError("upstream chat response is missing assistant message")

    content = message.get("content")
    tool_calls = message.get("tool_calls")
    native_items: list[dict[str, Any]] = []
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
                arguments = json.dumps(
                    arguments,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            item = _tool_call_item(
                wire_name=wire_name,
                arguments=arguments,
                call_id=call_id,
                tool_metadata=tool_metadata,
                require_known=recover_text_tool_calls,
            )
            if item is not None:
                native_items.append(item)

    if (
        recover_text_tool_calls
        and not native_items
        and isinstance(content, str)
        and content.strip()
    ):
        recovered = _recover_text_tool_calls(content, tool_metadata)
        if recovered is not None:
            return recovered

    items: list[dict[str, Any]] = []
    if isinstance(content, str) and content:
        items.append({
            "type": "message",
            "role": "assistant",
            "id": f"msg_{uuid4().hex}",
            "content": [{"type": "output_text", "text": content}],
        })
    items.extend(native_items)
    return items


def _tool_call_item(
    *,
    wire_name: str,
    arguments: str,
    call_id: str,
    tool_metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]],
    require_known: bool,
) -> dict[str, Any] | None:
    metadata = tool_metadata.get(wire_name)
    if metadata is None:
        if require_known:
            return None
        metadata = ("function", None, wire_name, {"type": "object"})

    kind, namespace, original_name, schema = metadata
    arguments = _normalize_tool_arguments(arguments, schema)
    if kind == "custom":
        custom_input = arguments
        try:
            decoded = json.loads(arguments)
            if isinstance(decoded, dict) and isinstance(decoded.get("input"), str):
                custom_input = decoded["input"]
        except json.JSONDecodeError:
            pass
        return {
            "type": "custom_tool_call",
            "call_id": call_id,
            "name": original_name,
            "input": custom_input,
        }

    item: dict[str, Any] = {
        "type": "function_call",
        "call_id": call_id,
        "name": original_name,
        "arguments": arguments,
    }
    if namespace:
        item["namespace"] = namespace
    return item


def _recover_text_tool_calls(
    content: str,
    tool_metadata: dict[str, tuple[str, str | None, str, dict[str, Any]]],
) -> list[dict[str, Any]] | None:
    """Promote pure textual tool-call JSON only when every call is allowed.

    Small local models sometimes print the tool invocation object instead of
    emitting a structured tool call. Recovery is intentionally all-or-nothing:
    prose, malformed JSON, or any tool not in the filtered metadata leaves the
    assistant text untouched.
    """

    decoded_calls = _decode_text_tool_call_sequence(content)
    if not decoded_calls:
        return None

    recovered: list[dict[str, Any]] = []
    for raw_call in decoded_calls:
        name = raw_call.get("name")
        if not isinstance(name, str) or name not in tool_metadata:
            return None

        raw_arguments = raw_call.get("parameters", raw_call.get("arguments", {}))
        kind = tool_metadata[name][0]
        if kind == "custom" and "input" in raw_call and "parameters" not in raw_call:
            raw_arguments = {"input": raw_call["input"]}

        if isinstance(raw_arguments, str):
            arguments = raw_arguments
        else:
            arguments = json.dumps(
                raw_arguments,
                ensure_ascii=False,
                separators=(",", ":"),
            )

        item = _tool_call_item(
            wire_name=name,
            arguments=arguments,
            call_id=f"call_{uuid4().hex}",
            tool_metadata=tool_metadata,
            require_known=True,
        )
        if item is None:
            return None
        recovered.append(item)

    return recovered


def _decode_text_tool_call_sequence(content: str) -> list[dict[str, Any]] | None:
    text = content.strip()
    if text.startswith("```") and text.endswith("```"):
        lines = text.splitlines()
        if len(lines) >= 3:
            text = "\n".join(lines[1:-1]).strip()

    decoder = json.JSONDecoder()
    calls: list[dict[str, Any]] = []
    position = 0
    while position < len(text):
        while position < len(text) and (
            text[position].isspace() or text[position] == ";"
        ):
            position += 1
        if position >= len(text):
            break
        try:
            value, position = decoder.raw_decode(text, position)
        except json.JSONDecodeError:
            return None
        if not isinstance(value, dict):
            return None
        calls.append(value)

    return calls or None


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



def _normalize_tool_arguments(arguments: str, schema: dict[str, Any]) -> str:
    """Repair weak-model JSON type mismatches using the client tool schema.

    Only fields whose declared JSON Schema type disagrees with the model output
    are considered. Values that already match their schema are preserved.
    """
    try:
        value = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments

    normalized = _coerce_to_schema(value, schema)
    return json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))


def _coerce_to_schema(value: Any, schema: Any) -> Any:
    if not isinstance(schema, dict):
        return value

    # Prefer the first union branch that already matches; otherwise try each
    # branch conservatively and accept a result whose type matches.
    for key in ("anyOf", "oneOf"):
        branches = schema.get(key)
        if isinstance(branches, list):
            for branch in branches:
                if isinstance(branch, dict) and _matches_schema_type(value, branch):
                    return _coerce_to_schema(value, branch)
            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                candidate = _coerce_to_schema(value, branch)
                if _matches_schema_type(candidate, branch):
                    return candidate
            return value

    expected = schema.get("type")
    if isinstance(expected, list):
        if any(_matches_json_type(value, item) for item in expected if isinstance(item, str)):
            for item in expected:
                if isinstance(item, str) and _matches_json_type(value, item):
                    expected = item
                    break
        else:
            expected = next(
                (item for item in expected if isinstance(item, str) and item != "null"),
                expected[0] if expected else None,
            )

    if expected == "object":
        candidate = value
        if isinstance(candidate, str):
            parsed = _parse_structured_string(candidate)
            if isinstance(parsed, dict):
                candidate = parsed
        if not isinstance(candidate, dict):
            return value
        properties = schema.get("properties")
        if not isinstance(properties, dict):
            return candidate
        result = dict(candidate)
        for key, child_schema in properties.items():
            if key in result:
                result[key] = _coerce_to_schema(result[key], child_schema)
        return result

    if expected == "array":
        candidate = value
        if isinstance(candidate, str):
            parsed = _parse_structured_string(candidate)
            if isinstance(parsed, (list, tuple)):
                candidate = list(parsed)
        if not isinstance(candidate, list):
            return value
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            return [_coerce_to_schema(item, item_schema) for item in candidate]
        return candidate

    if expected == "integer" and isinstance(value, str):
        try:
            stripped = value.strip()
            if stripped:
                return int(stripped, 10)
        except ValueError:
            return value

    if expected == "number" and isinstance(value, str):
        try:
            stripped = value.strip()
            if stripped:
                number = float(stripped)
                return int(number) if number.is_integer() else number
        except ValueError:
            return value

    if expected == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

    if expected == "null" and isinstance(value, str) and value.strip().lower() == "null":
        return None

    return value


def _parse_structured_string(value: str) -> Any:
    text = value.strip()
    if not text:
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        return ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return value


def _matches_schema_type(value: Any, schema: dict[str, Any]) -> bool:
    expected = schema.get("type")
    if isinstance(expected, list):
        return any(
            _matches_json_type(value, item)
            for item in expected
            if isinstance(item, str)
        )
    if isinstance(expected, str):
        return _matches_json_type(value, expected)
    return True


def _matches_json_type(value: Any, expected: str) -> bool:
    if expected == "object":
        return isinstance(value, dict)
    if expected == "array":
        return isinstance(value, list)
    if expected == "string":
        return isinstance(value, str)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    if expected == "null":
        return value is None
    return True
