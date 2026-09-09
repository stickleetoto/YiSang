import json

from yisang.context.compiler import ContextCompiler
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.server.proxy import YiSangModelProxy


def _proxy():
    memory = InMemoryMemoryPort()
    memory.commit(
        MemoryProposal(
            content="YiSang keeps memory outside the attached model",
            kind="semantic",
            source_engine="test",
            confidence=0.99,
            evidence=["test"],
        )
    )
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.repo.inspect",
            name="Repository Inspector",
            provides=("repository_analysis",),
            keywords=("repo", "repository"),
            instructions="Inspect repository evidence before changing code.",
        )
    )
    return YiSangModelProxy(
        model_id="yisang-qwen",
        upstream_model="qwen-upstream",
        identity=IdentityCharter("yisang-model", "YiSang"),
        state=AgentState(active_engine="qwen-upstream", active_project="YiSang"),
        memory=memory,
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
    )


def test_prepare_chat_preserves_client_tools_and_messages():
    proxy = _proxy()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "read a file",
                "parameters": {
                    "type": "object",
                    "properties": {"path": {"type": "string"}},
                    "required": ["path"],
                },
            },
        }
    ]
    original_messages = [
        {"role": "developer", "content": "Work in the current repository."},
        {"role": "user", "content": "Inspect this repo and continue the work."},
    ]
    prepared = proxy.prepare_chat_request(
        {
            "model": "yisang-qwen",
            "messages": original_messages,
            "tools": tools,
            "tool_choice": "auto",
            "temperature": 0.1,
        }
    )

    assert prepared.payload["model"] == "qwen-upstream"
    assert prepared.payload["tools"] == tools
    assert prepared.payload["tool_choice"] == "auto"
    assert prepared.payload["messages"][1:] == original_messages
    assert prepared.payload["messages"][0]["role"] == "system"
    assert "YISANG MODEL PROXY" in prepared.payload["messages"][0]["content"]
    assert "ego.repo.inspect" in prepared.payload["messages"][0]["content"]
    assert prepared.used_memory_ids
    assert prepared.used_ego_ids == ("ego.repo.inspect",)


def test_prepare_chat_rejects_unknown_model_alias():
    proxy = _proxy()
    try:
        proxy.prepare_chat_request(
            {"model": "raw-qwen", "messages": [{"role": "user", "content": "hi"}]}
        )
    except ValueError as exc:
        assert "unknown YiSang model" in str(exc)
    else:
        raise AssertionError("unknown model alias was accepted")


def test_user_intent_drives_ego_routing_over_large_system_prompt():
    proxy = _proxy()
    prepared = proxy.prepare_chat_request(
        {
            "model": "yisang-qwen",
            "messages": [
                {"role": "system", "content": "repository " * 4000},
                {"role": "user", "content": "say hello"},
            ],
        }
    )
    assert prepared.used_ego_ids == ()


def test_normalize_response_preserves_tool_calls():
    proxy = _proxy()
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": '{"path":"README.md"}'},
        }
    ]
    upstream = {
        "id": "chatcmpl-upstream",
        "object": "chat.completion",
        "model": "qwen-upstream",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": None, "tool_calls": tool_calls},
                "finish_reason": "tool_calls",
            }
        ],
    }
    normalized = proxy.normalize_chat_response(upstream)
    assert normalized["model"] == "yisang-qwen"
    assert normalized["choices"][0]["message"]["tool_calls"] == tool_calls
    assert upstream["model"] == "qwen-upstream"


def test_normalize_sse_line_rewrites_only_model_id():
    proxy = _proxy()
    event = {
        "id": "chunk-1",
        "object": "chat.completion.chunk",
        "model": "qwen-upstream",
        "choices": [{"index": 0, "delta": {"content": "hi"}}],
    }
    line = b"data: " + json.dumps(event).encode() + b"\n\n"
    normalized = proxy.normalize_sse_line(line)
    data = json.loads(normalized.strip()[5:].strip())
    assert data["model"] == "yisang-qwen"
    assert data["choices"] == event["choices"]
    assert proxy.normalize_sse_line(b"data: [DONE]\n\n") == b"data: [DONE]\n\n"
