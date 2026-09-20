from yisang.context.compiler import ContextCompiler
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.eval.continuity import (
    ContinuityProbe,
    build_continuity_report,
    evaluate_v06_closeout,
    run_continuity_case,
)
from yisang.identity.models import AgentState, IdentityCharter
from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    stable_knowledge_ref,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _runtime(*, active_engine: str, populated: bool):
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()
    library = None

    if populated:
        memory.commit(
            MemoryProposal(
                content="continuity probe remembers alpha",
                source_engine="seed",
                confidence=0.95,
                evidence=["continuity:seed"],
                trust_class="verified",
                writer="governor",
            )
        )
        egos.register(
            EgoManifest(
                ego_id="ego.debug",
                name="Debug",
                provides=("debug",),
                keywords=("debug", "continuity"),
            )
        )
        library = InMemoryLibraryPort(
            (
                Book(
                    book_id="continuity-book",
                    title="Continuity Algorithms",
                    version="1",
                    entries=(
                        KnowledgeEntry(
                            entry_id="continuity-entry",
                            title="Dijkstra Continuity Probe",
                            summary="Priority-queue shortest path knowledge.",
                            aliases=("shortest path",),
                            tags=("continuity", "dijkstra"),
                            source_refs=("book://continuity",),
                            trust_class="curated",
                            validation_state="validated",
                        ),
                    ),
                ),
            )
        )
        state = AgentState(
            active_engine=active_engine,
            active_project="YiSang",
            current_goal="prove Library continuity",
            tags={"phase": "v0.6"},
        )
    else:
        state = AgentState(active_engine=active_engine)

    engines = EngineRouter()
    engines.register(EchoEngine("engine-a", "A"))
    engines.register(EchoEngine("engine-b", "B"))

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=state,
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        library_port=library,
    )


def test_v06_continuity_proves_library_restore_and_retrieval():
    source = _runtime(active_engine="engine-a", populated=True)
    target = _runtime(active_engine="engine-a", populated=False)
    memory_id = source.memory.all()[0].memory_id
    knowledge_ref = stable_knowledge_ref(
        "continuity-book",
        "continuity-entry",
    )

    result = run_continuity_case(
        case_id="library-a-to-b",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        library_factory=InMemoryLibraryPort,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
        probe=ContinuityProbe(
            request_text="continuity debug alpha Dijkstra shortest path",
            expected_memory_ids=(memory_id,),
            expected_ego_ids=("ego.debug",),
            expected_knowledge_refs=(knowledge_ref,),
        ),
    )

    assert result.passed is True
    assert result.library_preserved is True
    assert result.source_expected_knowledge_retrieved is True
    assert result.expected_knowledge_retrieved is True
    assert result.source_used_knowledge_refs == (knowledge_ref,)
    assert result.used_knowledge_refs == (knowledge_ref,)


def test_v06_closeout_requires_library_evidence():
    source = _runtime(active_engine="engine-a", populated=True)
    target = _runtime(active_engine="engine-a", populated=False)
    knowledge_ref = stable_knowledge_ref(
        "continuity-book",
        "continuity-entry",
    )
    result = run_continuity_case(
        case_id="library-closeout",
        source_runtime=source,
        target_runtime=target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        library_factory=InMemoryLibraryPort,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
        probe=ContinuityProbe(
            request_text="continuity debug Dijkstra shortest path",
            expected_knowledge_refs=(knowledge_ref,),
        ),
    )

    report = build_continuity_report(
        [result, result, result],
        metadata={
            "source_model": "model-a",
            "target_model": "model-b",
            "source_family": "llama",
            "target_family": "qwen",
            "library_probe": True,
        },
    )
    check = evaluate_v06_closeout(report)

    assert check.ready is True
    assert check.errors == ()
