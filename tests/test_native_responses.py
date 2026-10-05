from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

import pytest

from yisang.server.native_responses import (
    normalize_native_responses_response,
    prepare_native_responses_request,
)
from yisang.server.responses_upstream import OpenAIResponsesUpstream


class FakeProxy:
    model_id = "yisang-luna"
    upstream_model = "gpt-6-luna"

    def __init__(self) -> None:
        self.seen_chat_payload = None

    def prepare_chat_request(self, payload):
        self.seen_chat_payload = deepcopy(payload)
        return SimpleNamespace(
            request_id="ysreq-test",
            payload={
                "model": self.upstream_model,
                "messages": [
                    {
                        "role": "system",
                        "content": "[YISANG MODEL PROXY]\nAUGMENTED CONTEXT",
                    },
                    *deepcopy(payload["messages"]),
                ],
            },
        )


def _mcp_namespace_tool():
    return {
        "type": "namespace",
        "name": "mcp_hand",
        "description": "Windows computer use",
        "tools": [
            {
                "type": "function",
                "name": "window",
                "description": "Window operations",
                "parameters": {
                    "type": "object",
                    "properties": {"action": {"type": "string"}},
                    "required": ["action"],
                },
            }
        ],
    }


def test_native_responses_preserves_payload_and_forces_xhigh_pro():
    proxy = FakeProxy()
    original_input = [
        {
            "type": "message",
            "role": "user",
            "content": [{"type": "input_text", "text": "Inspect the repo"}],
        },
        {
            "type": "function_call",
            "call_id": "call-old",
            "name": "exec_command",
            "arguments": '{"cmd":"git status"}',
        },
        {
            "type": "function_call_output",
            "call_id": "call-old",
            "output": "clean",
        },
    ]
    tools = [
        {
            "type": "function",
            "name": "exec_command",
            "description": "Run shell",
            "parameters": {"type": "object"},
        },
        _mcp_namespace_tool(),
    ]
    payload = {
        "model": "yisang-luna",
        "instructions": "Follow repository rules.",
        "input": deepcopy(original_input),
        "tools": deepcopy(tools),
        "reasoning": {"effort": "medium", "summary": "auto"},
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": True,
    }

    prepared = prepare_native_responses_request(
        proxy,
        payload,
        tool_profile="full",
        reasoning_effort="xhigh",
        reasoning_mode="pro",
    )

    assert prepared.request_id == "ysreq-test"
    assert prepared.stream is True
    assert prepared.payload["stream"] is False
    assert prepared.payload["model"] == "gpt-6-luna"
    assert prepared.payload["input"] == original_input
    assert prepared.payload["tools"] == tools
    assert prepared.payload["reasoning"] == {
        "effort": "xhigh",
        "summary": "auto",
        "mode": "pro",
    }
    assert "temperature" not in prepared.payload
    assert "top_p" not in prepared.payload
    assert prepared.payload["instructions"].startswith(
        "[YISANG MODEL PROXY]\nAUGMENTED CONTEXT"
    )
    assert prepared.payload["instructions"].endswith("Follow repository rules.")

    # Retrieval augmentation uses user intent, not tool outputs, and does not
    # alter the authoritative native Responses input sent upstream.
    assert proxy.seen_chat_payload["model"] == "yisang-luna"
    assert any(
        message["role"] == "user" and "Inspect the repo" in message["content"]
        for message in proxy.seen_chat_payload["messages"]
    )


def test_native_responses_full_profile_keeps_mcp_namespace():
    proxy = FakeProxy()
    tool = _mcp_namespace_tool()
    prepared = prepare_native_responses_request(
        proxy,
        {
            "model": "yisang-luna",
            "input": "Use mcp-hand",
            "tools": [tool],
        },
        tool_profile="full",
        reasoning_effort="xhigh",
        reasoning_mode="pro",
    )

    assert prepared.payload["tools"] == [tool]


def test_native_responses_small_profile_still_restricts_tools():
    proxy = FakeProxy()
    prepared = prepare_native_responses_request(
        proxy,
        {
            "model": "yisang-luna",
            "input": "Work locally",
            "tools": [
                {
                    "type": "function",
                    "name": "exec_command",
                    "parameters": {"type": "object"},
                },
                _mcp_namespace_tool(),
            ],
        },
        tool_profile="codex-small",
    )

    assert [tool["name"] for tool in prepared.payload["tools"]] == ["exec_command"]
    assert prepared.payload["parallel_tool_calls"] is False


def test_native_response_normalization_preserves_reasoning_and_tool_items():
    proxy = FakeProxy()
    upstream = {
        "id": "resp-upstream",
        "object": "response",
        "model": "gpt-6-luna",
        "status": "completed",
        "reasoning": {"effort": "xhigh", "mode": "pro"},
        "output": [
            {"type": "reasoning", "id": "rs_1", "summary": []},
            {
                "type": "function_call",
                "call_id": "call-1",
                "name": "window",
                "arguments": '{"action":"server_info"}',
            },
        ],
        "usage": {
            "input_tokens": 100,
            "output_tokens": 50,
            "output_tokens_details": {"reasoning_tokens": 40},
            "total_tokens": 150,
        },
    }

    normalized = normalize_native_responses_response(proxy, upstream)

    assert normalized["model"] == "yisang-luna"
    assert normalized["output"] == upstream["output"]
    assert normalized["reasoning"] == upstream["reasoning"]
    assert normalized["usage"] == upstream["usage"]
    assert upstream["model"] == "gpt-6-luna"


@pytest.mark.parametrize("effort", ["ultra", "maximum"])
def test_native_responses_rejects_unknown_reasoning_effort(effort):
    with pytest.raises(ValueError, match="reasoning effort"):
        prepare_native_responses_request(
            FakeProxy(),
            {"model": "yisang-luna", "input": "hello"},
            reasoning_effort=effort,
        )


def test_responses_upstream_targets_responses_endpoint():
    upstream = OpenAIResponsesUpstream(
        base_url="https://apirouter.example/v1/",
        api_key="secret",
        timeout=321,
    )

    assert upstream.responses_url == "https://apirouter.example/v1/responses"
    assert upstream.timeout == 321
