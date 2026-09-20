from __future__ import annotations

import argparse
import json

from .generalizer import ExperienceGeneralizer
from .models import ExperienceEpisode, ExperienceEvidence
from .promotion import PromotionGate
from .replay import ReplayPlanBuilder


def _episode(index: int) -> ExperienceEpisode:
    return ExperienceEpisode(
        episode_id=f"generalization-smoke-{index}",
        outcome="success",
        summary="pytest repair completed",
        evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:generalization-smoke:{index}",
                source_type="test_result",
                summary="source episode was independently verified",
                verified=True,
            ),
        ),
        trigger_conditions=("python test failure",),
        procedure_steps=(
            "tool:pytest",
            "inspect:failing_test",
            "apply:minimal_patch",
            "tool:pytest",
        ),
        engine_id="smoke-engine",
        verification_status="PASS",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-generalization-smoke")
    parser.parse_args(argv)
    episodes = tuple(_episode(index) for index in range(1, 4))
    candidate = ExperienceGeneralizer(min_repeats=3).generalize(
        episodes, kind="procedure", target="ego_procedure", scope="coding"
    )
    builder = ReplayPlanBuilder()
    plan = builder.build(candidate, episodes)
    report = builder.report(
        plan,
        {case.test_id: True for case in plan.cases},
        evidence_refs={
            case.test_id: (f"replay-proof:{case.source_episode_id}",)
            for case in plan.cases
        },
    )
    outcome = PromotionGate(min_success_count=3).promote(candidate, report)
    payload = {
        "ready": bool(
            outcome.decision.accepted
            and outcome.artifact is not None
            and len(plan.cases) == 3
        ),
        "source_episode_count": len(episodes),
        "candidate_id": candidate.candidate_id,
        "candidate_kind": candidate.kind,
        "success_count": candidate.success_count,
        "shared_triggers": list(candidate.trigger_conditions),
        "replay_case_count": len(plan.cases),
        "replay_strategy": plan.strategy,
        "simulated_replay_results": True,
        "promotion_accepted": outcome.decision.accepted,
        "promotion_reason": outcome.decision.reason,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
