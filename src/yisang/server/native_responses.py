from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .proxy import YiSangModelProxy

_ALLOWED_REASONING_EFFORTS = {
    "none",
    "minimal",
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
}
_ALLOWED_REASONING_MODES = {"standard", "pro"}
_CODEX_SMALL_ALLOWED_TOOLS = frozenset({"exec_command", "apply_patch"})


@dataclass(frozen=True)
class PreparedNativeResponsesRequest:
    request_id: str
    payload: dict[str, Any]
    stream: bool


def prepare_native_responses_request(
    proxy: YiSangModelProxy,
    payload: dict[str, Any],
    *,
    tool_profile: str = "full",
    reasoning_effort: str | None = None,
    reasoning_mode: str | None = None,
) -> PreparedNativeResponsesRequest:
    """Prepare a Responses request without translating it to Chat Completions.

    The client Responses payload remains authoritative for tool schemas and
    continuation items. YiSang only injects its augmentation context, rewrites
    the public model alias to the upstream model, applies the optional tool
    profile, and enforces explicitly configured reasoning settings.
    """

    if not isinstance(payload, dict):
        raise ValueError("request body must be a JSON object")

    model = payload.get("model")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("model must be a non-empty string")
    if model != proxy.model_id:
        raise ValueError(f"unknown YiSang model: {model}")

    if tool_profile not in {"full", "codex-small"}:
        raise ValueError(f"unknown tool profile: {tool_profile}")
    if (
        reasoning_effort is not None
        and reasoning_effort not in _ALLOWED_REASONING_EFFORTS
    ):
        raise ValueError(f"unsupported reasoning effort: {reasoning_effort}")
    if reasoning_mode is not None and reasoning_mode not in _ALLOWED_REASONING_MODES:
        raise ValueError(f"unsupported reasoning mode: {reasoning_mode}")

    retrieval_messages = _responses_retrieval_messages(payload)
    if not retrieval_messages:
        retrieval_messages = [{"role": "user", "content": "conversation continuation"}]

    prepared_chat = proxy.prepare_chat_request(
        {
            "model": proxy.model_id,
            "messages": retrieval_messages,
            "stream": False,
        }
    )
    augmentation = prepared_chat.payload["messages"][0]["content"]

    upstream_payload = deepcopy(payload)
    upstream_payload["model"] = proxy.upstream_model

    # YiSang buffers the upstream response so it can normalize the public
    # model alias and emit the small canonical SSE surface Codex already uses.
    client_stream = bool(upstream_payload.get("stream", False))
    upstream_payload["stream"] = False

    existing_instructions = upstream_payload.get("instructions")
    if isinstance(existing_instructions, str) and existing_instructions.strip():
        upstream_payload["instructions"] = (
            f"{augmentation}\n\n"
            "[CLIENT INSTRUCTIONS]\n"
            f"{existing_instructions}"
        )
    else:
        upstream_payload["instructions"] = augmentation

    if tool_profile == "codex-small":
        upstream_payload["tools"] = _filter_codex_small_tools(
            upstream_payload.get("tools")
        )
        upstream_payload["parallel_tool_calls"] = False

    reasoning = upstream_payload.get("reasoning")
    reasoning_payload = dict(reasoning) if isinstance(reasoning, dict) else {}
    if reasoning_effort is not None:
        reasoning_payload["effort"] = reasoning_effort
    if reasoning_mode is not None:
        reasoning_payload["mode"] = reasoning_mode
    if reasoning_payload:
        upstream_payload["reasoning"] = reasoning_payload

    effective_effort = reasoning_payload.get("effort")
    if isinstance(effective_effort, str) and effective_effort != "none":
        # GPT-6 reasoning requests must not carry sampling controls that conflict
        # with reasoning execution. Keep the native Responses request conservative.
        upstream_payload.pop("temperature", None)
        upstream_payload.pop("top_p", None)
        upstream_payload.pop("top_logprobs", None)
        upstream_payload.pop("logprobs", None)

    return PreparedNativeResponsesRequest(
        request_id=prepared_chat.request_id,
        payload=upstream_payload,
        stream=client_stream,
    )


def normalize_native_responses_response(
    proxy: YiSangModelProxy,
    response: dict[str, Any],
) -> dict[str, Any]:
    """Preserve native Responses output while hiding the upstream model id."""

    if not isinstance(response, dict):
        raise ValueError("upstream response must be a JSON object")
    normalized = deepcopy(response)
    normalized["model"] = proxy.model_id
    return normalized


def _responses_retrieval_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    messages: list[dict[str, Any]] = []

    instructions = payload.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        messages.append({"role": "system", "content": instructions})

    raw_input = payload.get("input")
    if isinstance(raw_input, str):
        if raw_input.strip():
            messages.append({"role": "user", "content": raw_input})
        return messages

    if not isinstance(raw_input, list):
        return messages

    for item in raw_input[-16:]:
        if isinstance(item, str):
            if item.strip():
                messages.append({"role": "user", "content": item})
            continue
        if not isinstance(item, dict):
            continue

        item_type = item.get("type")
        role = item.get("role")
        if item_type != "message" and role is None:
            continue
        if role not in {"system", "developer", "user", "assistant"}:
            continue

        text = _content_text(item.get("content"))
        if not text:
            continue
        mapped_role = "system" if role == "developer" else role
        messages.append({"role": mapped_role, "content": text})

    return messages


def _content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("text", "input_text", "output_text"):
            value = item.get(key)
            if isinstance(value, str):
                parts.append(value)
                break
    return "\n".join(parts)


def _filter_codex_small_tools(raw_tools: Any) -> list[dict[str, Any]]:
    if raw_tools is None:
        return []
    if not isinstance(raw_tools, list):
        raise ValueError("tools must be a list")

    filtered: list[dict[str, Any]] = []
    for tool in raw_tools:
        if not isinstance(tool, dict):
            continue
        tool_type = tool.get("type")
        if tool_type in {"function", "custom"}:
            if tool.get("name") in _CODEX_SMALL_ALLOWED_TOOLS:
                filtered.append(deepcopy(tool))
            continue

        if tool_type == "namespace":
            children = tool.get("tools")
            if not isinstance(children, list):
                continue
            kept = [
                deepcopy(child)
                for child in children
                if (
                    isinstance(child, dict)
                    and child.get("type") == "function"
                    and child.get("name") in _CODEX_SMALL_ALLOWED_TOOLS
                )
            ]
            if kept:
                namespace = deepcopy(tool)
                namespace["tools"] = kept
                filtered.append(namespace)

    return filtered
