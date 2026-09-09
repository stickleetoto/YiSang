from yisang.context.compiler import ContextCompiler
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.execution.models import ActionProposal
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.server.gateway import YiSangModelGateway
from yisang.server.protocol import ProtocolError


class CapturingEngine(LLMEngine):
    engine_id = "capture"

    def __init__(self, *, action=False):
        self.action = action
        self.context = None

    def generate(self, context):
        self.context = context
        actions = [ActionProposal("shell", {"command": "pwd"})] if self.action else []
        return EngineResult(
            engine_id=self.engine_id,
            text="answer",
            action_proposals=actions,
            metadata={"model": "qwen-test", "usage": {"prompt_tokens": 10, "completion_tokens": 2}},
        )


def make_gateway(*, action=False):
    engine = CapturingEngine(action=action)
    engines = EngineRouter()
    engines.register(engine)
    gateway = YiSangModelGateway(
        model_id="yisang-qwen",
        identity=IdentityCharter("yisang-test", "YiSang"),
        state=AgentState(active_engine="capture"),
        memory=InMemoryMemoryPort(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
    )
    return gateway, engine


def test_chat_completion_preserves_roles_and_identity_context():
    gateway, engine = make_gateway()
    response = gateway.chat_completions({
        "model": "yisang-qwen",
        "messages": [
            {"role": "developer", "content": "follow project rules"},
            {"role": "user", "content": "fix the repo"},
        ],
    })
    assert response["choices"][0]["message"]["content"] == "answer"
    assert response["model"] == "yisang-qwen"
    assert "[DEVELOPER]" in engine.context.user_text
    assert "fix the repo" in engine.context.user_text


def test_chat_tools_are_delegated_back_to_client():
    gateway, engine = make_gateway(action=True)
    response = gateway.chat_completions({
        "model": "yisang-qwen",
        "messages": [{"role": "user", "content": "check cwd"}],
        "tools": [{
            "type": "function",
            "function": {
                "name": "shell",
                "description": "run shell command",
                "parameters": {
                    "type": "object",
                    "properties": {"command": {"type": "string"}},
                    "required": ["command"],
                },
            },
        }],
    })
    call = response["choices"][0]["message"]["tool_calls"][0]
    assert call["function"]["name"] == "shell"
    assert response["choices"][0]["finish_reason"] == "tool_calls"
    assert engine.context.tools[0]["tool_id"] == "shell"
    assert engine.context.tools[0]["delegated"] is True


def test_responses_api_returns_function_call_items():
    gateway, _ = make_gateway(action=True)
    response = gateway.responses({
        "model": "yisang-qwen",
        "input": "check cwd",
        "tools": [{
            "type": "function",
            "name": "shell",
            "description": "run shell command",
            "parameters": {"type": "object"},
        }],
    })
    calls = [item for item in response["output"] if item["type"] == "function_call"]
    assert calls[0]["name"] == "shell"
    assert response["object"] == "response"
    assert response["status"] == "completed"


def test_unknown_model_is_rejected():
    gateway, _ = make_gateway()
    try:
        gateway.chat_completions({
            "model": "raw-qwen",
            "messages": [{"role": "user", "content": "hi"}],
        })
    except ProtocolError as exc:
        assert exc.code == "model_not_found"
        assert exc.status == 404
    else:
        raise AssertionError("unknown model was accepted")


def test_streaming_is_fail_closed_until_implemented():
    gateway, _ = make_gateway()
    try:
        gateway.responses({"model": "yisang-qwen", "input": "hi", "stream": True})
    except ProtocolError as exc:
        assert exc.code == "streaming_not_supported"
    else:
        raise AssertionError("unsupported streaming was accepted")
