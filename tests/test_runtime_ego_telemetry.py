from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.ego.telemetry_memory import InMemoryEgoTelemetryPort
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier


def test_runtime_records_selected_ego_outcome_telemetry():
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.python",
            name="Python",
            provides=("python",),
            keywords=("python",),
            version="1.0.0",
        )
    )
    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))
    telemetry = InMemoryEgoTelemetryPort()
    runtime = YiSangRuntime(
        identity=IdentityCharter("telemetry-runtime", "YiSang"),
        state=AgentState(active_engine="small"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        ego_telemetry_port=telemetry,
    )

    response = runtime.run(
        YiSangRequest("telemetry-request", "python help")
    )

    assert len(response.ego_telemetry_event_ids) == 1
    events = telemetry.events(
        ego_id="ego.python",
        version="1.0.0",
    )
    assert len(events) == 1
    assert events[0].success is True
    assert events[0].verification_status == "PASS"
    assert events[0].latency_ms is not None
