from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.execution.completion import ToolOutcome
from yisang.execution.models import ActionProposal
from yisang.execution.runtime import ActionRuntime
from yisang.execution.tools import ToolDefinition, ToolRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.action import ActionEvidenceVerifier
from yisang.verification.base import PassThroughVerifier
from yisang.verification.composite import CompositeVerifier


class CompletionAwareEngine(LLMEngine):
    engine_id = "completion-aware"
    supports_action_feedback = True

    def __init__(self):
        self.calls = 0

    def generate(self, context):
        self.calls += 1
        return EngineResult(
            engine_id=self.engine_id,
            text="working",
            action_proposals=[
                ActionProposal(
                    "workspace.write_marker",
                    {"value": "ok"},
                    requested_by=self.engine_id,
                )
            ],
        )


def _runtime(engine, handler):
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.repo",
            name="Repo",
            provides=("repo_write",),
            keywords=("write", "marker"),
            permissions={"filesystem": "workspace"},
        )
    )

    engines = EngineRouter()
    engines.register(engine)

    tools = ToolRegistry()
    tools.register(
        ToolDefinition(
            tool_id="workspace.write_marker",
            handler=handler,
            required_capabilities=("repo_write",),
            required_permissions={"filesystem": "workspace"},
            side_effecting=False,
            argument_schema={
                "type": "object",
                "properties": {"value": {"type": "string"}},
                "required": ["value"],
                "additionalProperties": False,
            },
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
        max_action_rounds=3,
    )


def test_verified_tool_outcome_stops_feedback_loop():
    engine = CompletionAwareEngine()
    runtime = _runtime(
        engine,
        lambda args: ToolOutcome(
            output={"written": args["value"]},
            goal_satisfied=True,
            completion_text="Marker written.",
            evidence={"marker": args["value"]},
        ),
    )

    response = runtime.run(YiSangRequest("r1", "write marker"))

    assert engine.calls == 1
    assert response.text == "Marker written."
    assert response.verification_status == "PASS"
    assert response.action_results[0]["goal_satisfied"] is True
    assert response.action_results[0]["completion_evidence"] == {"marker": "ok"}


def test_plain_tool_result_preserves_feedback_loop():
    engine = CompletionAwareEngine()
    runtime = _runtime(engine, lambda args: {"written": args["value"]})

    response = runtime.run(YiSangRequest("r2", "write marker"))

    assert engine.calls == 4
    assert response.verification_status == "FAIL"
    assert response.action_results[-1]["gate_reason"] == "action_loop_limit"


def test_completion_text_requires_goal_satisfied():
    try:
        ToolOutcome(output="x", completion_text="done")
    except ValueError as exc:
        assert "goal_satisfied" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
