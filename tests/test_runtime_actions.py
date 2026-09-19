from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier


class ToolEngine(LLMEngine):
    engine_id = "tool-engine"

    def generate(self, context):
        return EngineResult(
            engine_id=self.engine_id,
            text="tool proposed",
            action_proposals=[ActionProposal("text.length", {"text": "abcd"})],
        )


def _runtime(with_action_runtime=True):
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.text",
            name="Text",
            provides=("text_stats",),
            keywords=("text",),
        )
    )

    engines = EngineRouter()
    engines.register(ToolEngine())

    action_runtime = None
    if with_action_runtime:
        tools = ToolRegistry()
        tools.register(
            ToolDefinition(
                tool_id="text.length",
                handler=lambda args: len(args["text"]),
                required_capabilities=("text_stats",),
            )
        )
        action_runtime = ActionRuntime(tools=tools)

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="tool-engine"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        action_runtime=action_runtime,
    )


def test_runtime_executes_tool_only_through_action_layer():
    response = _runtime().run(YiSangRequest("r1", "text stats please"))
    assert response.action_results[0]["status"] == "EXECUTED"
    assert response.action_results[0]["output"] == 4
    assert response.action_results[0]["ego_id"] == "ego.text"


def test_runtime_denies_actions_when_execution_layer_missing():
    response = _runtime(False).run(YiSangRequest("r2", "text stats please"))
    assert response.action_results[0]["status"] == "DENIED"
    assert response.action_results[0]["gate_reason"] == "action_runtime_not_configured"
