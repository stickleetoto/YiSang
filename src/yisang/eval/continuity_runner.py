from __future__ import annotations

import argparse
import json

from yisang.context.compiler import ContextCompiler
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.openai_compatible import OpenAICompatibleEngine
from yisang.engines.router import EngineRouter
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

from .continuity import (
    ContinuityProbe,
    build_continuity_report,
    evaluate_v06_closeout,
    run_continuity_case,
    write_continuity_report,
)


def _build_runtime(
    *,
    engine: OpenAICompatibleEngine,
    populated: bool,
) -> YiSangRuntime:
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()
    library = None

    if populated:
        memory.commit(
            MemoryProposal(
                content="YiSang continuity probe token alpha",
                source_engine="continuity-seed",
                confidence=0.99,
                evidence=["continuity:seed"],
                trust_class="verified",
                importance=1.0,
                writer="continuity-runner",
            )
        )
        egos.register(
            EgoManifest(
                ego_id="ego.continuity",
                name="Continuity",
                provides=("continuity",),
                keywords=("continuity", "alpha", "debug"),
                instructions=(
                    "Preserve externalized identity and evidence boundaries."
                ),
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
                            summary=(
                                "A priority queue supports non-negative "
                                "shortest-path continuity checks."
                            ),
                            aliases=("shortest path",),
                            tags=("continuity", "dijkstra", "graph"),
                            use_when=("edge weights are non-negative",),
                            source_refs=("book://continuity",),
                            trust_class="curated",
                            validation_state="validated",
                        ),
                    ),
                ),
            )
        )
        state = AgentState(
            active_engine=engine.engine_id,
            active_project="YiSang",
            current_goal="prove identity and Library continuity across engines",
            tags={"suite": "v0.6-live"},
        )
    else:
        state = AgentState(active_engine=engine.engine_id)

    engines = EngineRouter()
    engines.register(engine)

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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-continuity",
        description=(
            "Run YiSang v0.6 continuity, including Roland Library restore, "
            "against two OpenAI-compatible reasoning engines."
        ),
    )
    parser.add_argument("--source-base-url", required=True)
    parser.add_argument("--source-model", required=True)
    parser.add_argument("--source-engine-id", default="engine-source")
    parser.add_argument("--source-family")
    parser.add_argument("--source-api-key")

    parser.add_argument("--target-base-url", required=True)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--target-engine-id", default="engine-target")
    parser.add_argument("--target-family")
    parser.add_argument("--target-api-key")

    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=64,
        help="Bound each continuity probe response to avoid runaway local generations.",
    )
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.repeats <= 0:
        raise SystemExit("--repeats must be positive")
    if args.max_tokens <= 0:
        raise SystemExit("--max-tokens must be positive")

    results = []
    for index in range(args.repeats):
        source_engine = OpenAICompatibleEngine(
            engine_id=args.source_engine_id,
            base_url=args.source_base_url,
            model=args.source_model,
            api_key=args.source_api_key,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            structured_actions=False,
        )
        target_engine = OpenAICompatibleEngine(
            engine_id=args.target_engine_id,
            base_url=args.target_base_url,
            model=args.target_model,
            api_key=args.target_api_key,
            timeout=args.timeout,
            temperature=args.temperature,
            max_tokens=args.max_tokens,
            structured_actions=False,
        )

        source = _build_runtime(engine=source_engine, populated=True)
        target = _build_runtime(engine=target_engine, populated=False)
        memory_id = source.memory.all()[0].memory_id

        try:
            result = run_continuity_case(
                case_id=f"live-{index + 1}",
                source_runtime=source,
                target_runtime=target,
                target_engine=args.target_engine_id,
                memory_factory=InMemoryMemoryPort,
                library_factory=InMemoryLibraryPort,
                policy_version="memory-governance-v1",
                runtime_version="0.6-live",
                probe=ContinuityProbe(
                    request_text=(
                        "continuity alpha debug Dijkstra shortest path"
                    ),
                    expected_memory_ids=(memory_id,),
                    expected_ego_ids=("ego.continuity",),
                    expected_knowledge_refs=(
                        stable_knowledge_ref(
                            "continuity-book",
                            "continuity-entry",
                        ),
                    ),
                ),
            )
        except TimeoutError as exc:
            raise SystemExit(
                "continuity probe timed out. Warm both models first, "
                "or increase --timeout. The runner now bounds probe output "
                "with --max-tokens."
            ) from exc
        results.append(result)

    report = build_continuity_report(
        results,
        metadata={
            "source_engine_id": args.source_engine_id,
            "target_engine_id": args.target_engine_id,
            "source_model": args.source_model,
            "target_model": args.target_model,
            "source_family": args.source_family,
            "target_family": args.target_family,
            "source_base_url": args.source_base_url,
            "target_base_url": args.target_base_url,
            "repeats": args.repeats,
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
            "library_probe": True,
        },
    )
    closeout = evaluate_v06_closeout(report)
    output = write_continuity_report(report, args.output)
    payload = report.to_dict()
    print(output)
    print(
        json.dumps(
            {
                "case_count": payload["case_count"],
                "pass_rate": payload["pass_rate"],
                "all_passed": payload["all_passed"],
                "source_engine": args.source_engine_id,
                "target_engine": args.target_engine_id,
                "source_model": args.source_model,
                "target_model": args.target_model,
                "source_family": args.source_family,
                "target_family": args.target_family,
                "closeout_ready": closeout.ready,
                "closeout_errors": list(closeout.errors),
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
