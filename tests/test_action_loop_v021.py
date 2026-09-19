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
from yisang.verification.action import ActionEvidenceVerifier
from yisang.verification.base import PassThroughVerifier
from yisang.verification.composite import CompositeVerifier


class FeedbackEngine(LLMEngine):
    engine_id = "feedback"
    supports_action_feedback = True

    def __init__(self):
        self.calls = 0
        self.contexts = []

    def generate(self, context):
        self.calls += 1
        self.contexts.append(context)
        if self.calls == 1:
            return EngineResult(
                engine_id=self.engine_id,
                text="checking",
                action_proposals=[
                    ActionProposal(
                        "workspace.read_text",
                        {"path": "README.md"},
                        requested_by=self.engine_id,
                    )
                ],
            )
        return EngineResult(engine_id=self.engine_id, text="final answer")


class LoopingEngine(LLMEngine):
    engine_id = "looping"
    supports_action_feedback = True

    def generate(self, context):
        return EngineResult(
            engine_id=self.engine_id,
            text="again",
            action_proposals=[
                ActionProposal(
                    "workspace.read_text",
                    {"path": "README.md"},
                    requested_by=self.engine_id,
                )
            ],
        )


def _runtime(engine, *, max_action_rounds=3):
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.repo",
            name="Repository Inspector",
            provides=("repository_analysis",),
            keywords=("repo", "read"),
            permissions={"filesystem": "read"},
        )
    )

    engines = EngineRouter()
    engines.register(engine)

    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="workspace.read_text",
            handler=lambda args: "hello from README",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
        )
    )

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine=engine.engine_id),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=CompositeVerifier(
            [PassThroughVerifier(), ActionEvidenceVerifier()]
        ),
        action_runtime=ActionRuntime(tools=tools),
        max_action_rounds=max_action_rounds,
    )


def test_successful_action_result_is_fed_back_for_final_reasoning():
    engine = FeedbackEngine()
    response = _runtime(engine).run(YiSangRequest("r1", "read repo README"))

    assert response.text == "final answer"
    assert response.verification_status == "PASS"
    assert engine.calls == 2
    assert engine.contexts[0].tools[0]["tool_id"] == "workspace.read_text"
    assert (
        engine.contexts[1].action_history[0]["result"]["output"]
        == "hello from README"
    )


def test_action_loop_limit_fails_closed():
    response = _runtime(
        LoopingEngine(),
        max_action_rounds=1,
    ).run(YiSangRequest("r2", "read repo README"))

    assert response.verification_status == "FAIL"
    assert response.action_results[-1]["status"] == "DENIED"
    assert response.action_results[-1]["gate_reason"] == "action_loop_limit"
