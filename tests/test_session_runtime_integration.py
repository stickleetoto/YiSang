from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.session.in_memory import InMemorySessionPort
from yisang.verification.base import PassThroughVerifier


class CaptureEngine(LLMEngine):
    engine_id = "capture"

    def __init__(self):
        self.contexts = []

    def generate(self, context):
        self.contexts.append(context)
        return EngineResult(
            engine_id=self.engine_id,
            text=f"reply-{len(self.contexts)}",
        )


def _runtime(engine, sessions):
    engines = EngineRouter()
    engines.register(engine)
    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine=engine.engine_id),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        session_port=sessions,
    )


def test_runtime_replays_prior_session_without_promoting_it_to_memory():
    sessions = InMemorySessionPort()
    engine = CaptureEngine()
    runtime = _runtime(engine, sessions)

    runtime.run(
        YiSangRequest(
            "r1",
            "first turn",
            metadata={"session_id": "session-a"},
        )
    )
    assert engine.contexts[0].session_history == []
    assert runtime.memory.all() == []

    runtime.run(
        YiSangRequest(
            "r2",
            "second turn",
            metadata={"session_id": "session-a"},
        )
    )

    history = engine.contexts[1].session_history
    assert [item["role"] for item in history] == ["user", "assistant"]
    assert [item["content"] for item in history] == ["first turn", "reply-1"]
    assert runtime.memory.all() == []

    persisted = sessions.history("session-a")
    assert [item.role for item in persisted] == [
        "user",
        "assistant",
        "user",
        "assistant",
    ]


def test_different_session_ids_do_not_cross_contaminate_context():
    sessions = InMemorySessionPort()
    engine = CaptureEngine()
    runtime = _runtime(engine, sessions)

    runtime.run(
        YiSangRequest("r1", "alpha", metadata={"session_id": "a"})
    )
    runtime.run(
        YiSangRequest("r2", "beta", metadata={"session_id": "b"})
    )

    assert engine.contexts[1].session_history == []


def test_request_without_session_id_preserves_one_shot_behavior():
    sessions = InMemorySessionPort()
    engine = CaptureEngine()
    runtime = _runtime(engine, sessions)

    runtime.run(YiSangRequest("r1", "one shot"))

    assert sessions.session_ids() == []
    assert engine.contexts[0].session_history == []


def test_context_budget_report_accounts_for_session_history():
    compiler = ContextCompiler()
    compiled = compiler.compile_with_report(
        request=YiSangRequest("r", "current"),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="test"),
        memories=[],
        egos=[],
        session_history=[
            {"sequence": 1, "role": "user", "content": "old"},
            {"sequence": 2, "role": "assistant", "content": "reply"},
        ],
    )

    assert compiled.budget.selected_session_messages == 2
    assert compiled.budget.dropped_session_messages == 0
    assert compiled.budget.session_chars > 0
