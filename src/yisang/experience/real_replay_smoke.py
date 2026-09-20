from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from .executor import (
    DeterministicReplayExecutor,
    FileExpectation,
    ReplayExecutionSpec,
)
from .generalizer import ExperienceGeneralizer
from .models import ExperienceEpisode, ExperienceEvidence
from .promotion import PromotionGate
from .replay import ReplayPlanBuilder


def _episode(index: int) -> ExperienceEpisode:
    return ExperienceEpisode(
        episode_id=f"real-replay-smoke-{index}",
        outcome="success",
        summary="deterministic file replay completed",
        evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:real-replay-source:{index}",
                source_type="test_result",
                summary="source episode independently verified",
                verified=True,
            ),
        ),
        trigger_conditions=("deterministic file replay",),
        procedure_steps=("tool:python", "verify:result.txt"),
        engine_id="smoke-engine",
        verification_status="PASS",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-real-replay-smoke")
    parser.parse_args(argv)

    episodes = tuple(_episode(index) for index in range(1, 4))
    candidate = ExperienceGeneralizer(min_repeats=3).generalize(
        episodes,
        kind="procedure",
        target="ego_procedure",
        scope="coding",
    )
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with TemporaryDirectory(prefix="yisang-replay-root-") as root:
        executor = DeterministicReplayExecutor(
            allowed_executables=(sys.executable,),
            workspace_root=Path(root),
        )
        specs = tuple(
            ReplayExecutionSpec(
                test_id=case.test_id,
                argv=(
                    sys.executable,
                    "-c",
                    (
                        "from pathlib import Path; "
                        "Path('result.txt').write_text('REPLAY_OK', encoding='utf-8'); "
                        "print('replay-ok')"
                    ),
                ),
                stdout_contains=("replay-ok",),
                file_expectations=(
                    FileExpectation(
                        path="result.txt",
                        exact_text="REPLAY_OK",
                    ),
                ),
            )
            for case in plan.cases
        )
        report = executor.execute(plan, specs)

    outcome = PromotionGate(min_success_count=3).promote(candidate, report)
    payload = {
        "ready": bool(
            outcome.decision.accepted
            and outcome.artifact is not None
            and all(result.passed for result in report.results)
        ),
        "source_episode_count": len(episodes),
        "replay_case_count": len(report.results),
        "executed_subprocess_replays": len(report.results),
        "all_replays_passed": all(result.passed for result in report.results),
        "evidence_refs_present": all(
            result.evidence_refs for result in report.results
        ),
        "shell_used": False,
        "promotion_accepted": outcome.decision.accepted,
        "promotion_reason": outcome.decision.reason,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
