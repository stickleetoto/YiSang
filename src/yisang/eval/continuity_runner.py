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
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier

from .continuity import (
    ContinuityProbe,
    build_continuity_report,
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
        state = AgentState(
            active_engine=engine.engine_id,
            active_project="YiSang",
            current_goal="prove identity continuity across engines",
            tags={"suite": "v0.5-live"},
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
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-continuity",
        description=(
            "Run YiSang v0.5 continuity against two OpenAI-compatible "
            "reasoning engines."
        ),
    )
    parser.add_argument("--source-base-url", required=True)
    parser.add_argument("--source-model", required=True)
    parser.add_argument("--source-engine-id", default="engine-source")
    parser.add_argument("--source-api-key")

    parser.add_argument("--target-base-url", required=True)
    parser.add_argument("--target-model", required=True)
    parser.add_argument("--target-engine-id", default="engine-target")
    parser.add_argument("--target-api-key")

    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--output", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.repeats <= 0:
        raise SystemExit("--repeats must be positive")

    results = []
    for index in range(args.repeats):
        source_engine = OpenAICompatibleEngine(
            engine_id=args.source_engine_id,
            base_url=args.source_base_url,
            model=args.source_model,
            api_key=args.source_api_key,
            timeout=args.timeout,
            temperature=args.temperature,
            structured_actions=False,
        )
        target_engine = OpenAICompatibleEngine(
            engine_id=args.target_engine_id,
            base_url=args.target_base_url,
            model=args.target_model,
            api_key=args.target_api_key,
            timeout=args.timeout,
            temperature=args.temperature,
            structured_actions=False,
        )

        source = _build_runtime(engine=source_engine, populated=True)
        target = _build_runtime(engine=target_engine, populated=False)
        memory_id = source.memory.all()[0].memory_id

        result = run_continuity_case(
            case_id=f"live-{index + 1}",
            source_runtime=source,
            target_runtime=target,
            target_engine=args.target_engine_id,
            memory_factory=InMemoryMemoryPort,
            policy_version="memory-governance-v1",
            runtime_version="0.5-live",
            probe=ContinuityProbe(
                request_text="continuity alpha debug",
                expected_memory_ids=(memory_id,),
                expected_ego_ids=("ego.continuity",),
            ),
        )
        results.append(result)

    report = build_continuity_report(results)
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
            },
            ensure_ascii=False,
        )
    )
    return 0 if report.all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
