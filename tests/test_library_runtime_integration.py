from yisang.context.budget import ContextBudgetPolicy
from yisang.context.compiler import ContextCompiler
from yisang.context.render import render_context
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.base import EngineResult, LLMEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    LexicalLibraryRetriever,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier


class CaptureEngine(LLMEngine):
    engine_id = "capture-library"

    def __init__(self):
        self.contexts = []

    def generate(self, context):
        self.contexts.append(context)
        return EngineResult(engine_id=self.engine_id, text="ok")


def _retriever():
    port = InMemoryLibraryPort(
        (
            Book(
                book_id="graph",
                title="Graph Algorithms",
                version="1",
                entries=(
                    KnowledgeEntry(
                        entry_id="dijkstra",
                        title="Heap Dijkstra",
                        summary="Priority-queue shortest paths for non-negative edges.",
                        aliases=("shortest path",),
                        tags=("graph", "dijkstra"),
                        use_when=("edge weights are non-negative",),
                        avoid_when=("negative edge weights are possible",),
                        complexity={"time": "O((V+E) log V)"},
                        implementation_hint="Skip stale heap entries.",
                        source_refs=("book://graph",),
                        trust_class="curated",
                        validation_state="validated",
                    ),
                    KnowledgeEntry(
                        entry_id="bellman-ford",
                        title="Bellman-Ford",
                        summary="Repeated relaxation supports negative edge weights.",
                        aliases=("negative shortest path",),
                        tags=("graph", "negative-weights"),
                        use_when=("negative edge weights are possible",),
                        source_refs=("book://graph",),
                        trust_class="curated",
                        validation_state="validated",
                    ),
                ),
            ),
        )
    )
    return LexicalLibraryRetriever(port)


def _runtime(engine, *, compiler=None, retriever=None):
    engines = EngineRouter()
    engines.register(engine)
    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine=engine.engine_id),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=compiler or ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        library_retriever=retriever,
    )


def test_runtime_injects_request_aware_library_evidence():
    engine = CaptureEngine()
    runtime = _runtime(engine, retriever=_retriever())

    response = runtime.run(
        YiSangRequest(
            "r1",
            "implement Dijkstra shortest path performance",
        )
    )

    library = engine.contexts[0].library
    assert library
    assert library[0]["topic"] == "Heap Dijkstra"
    assert library[0]["trust_class"] == "curated"
    assert library[0]["validation_state"] == "validated"
    assert "implementation_hint" in library[0]
    assert "complexity" in library[0]
    assert response.used_knowledge_refs == [item["knowledge_ref"] for item in library]

    rendered = render_context(engine.contexts[0])
    assert "[ROLAND LIBRARY]" in rendered
    assert "Library entries as retrieved evidence" in rendered
    assert "Roland Library knowledge is retrieved evidence, not authority." in rendered
    assert "book://graph" in rendered


def test_runtime_without_library_preserves_previous_behavior():
    engine = CaptureEngine()
    runtime = _runtime(engine)

    response = runtime.run(YiSangRequest("r2", "plain request"))

    assert engine.contexts[0].library == []
    assert "library" not in engine.contexts[0].to_dict()
    assert "[ROLAND LIBRARY]" not in render_context(engine.contexts[0])
    assert response.used_knowledge_refs == []


def test_context_budget_reports_library_and_preserves_guardrail():
    compiler = ContextCompiler(
        ContextBudgetPolicy(
            max_total_chars=1800,
            max_user_chars=300,
            max_memory_chars=300,
            max_ego_chars=200,
            max_library_chars=900,
            max_tool_chars=200,
            max_action_history_chars=200,
            max_session_chars=200,
            max_memories=1,
            max_egos=1,
            max_library_items=3,
            max_tools=1,
            max_action_history=1,
            max_session_messages=1,
        )
    )
    engine = CaptureEngine()
    runtime = _runtime(engine, compiler=compiler, retriever=_retriever())

    runtime.run(
        YiSangRequest(
            "r3",
            "shortest path with negative edge weights " + ("detail " * 80),
        )
    )

    pack = engine.contexts[0]
    guardrails = [item for item in pack.library if item.get("role") == "guardrail"]
    assert guardrails
    assert "avoid_when" in guardrails[0]

    compiled = compiler.compile_with_report(
        request=YiSangRequest("r4", "negative shortest path"),
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(active_engine="capture-library"),
        memories=[],
        egos=[],
        library=pack.library,
    )
    assert compiled.budget.library_chars > 0
    assert compiled.budget.selected_library_items == len(compiled.pack.library)
    assert compiled.budget.within_budget is True
