from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from yisang.execution.models import ActionProposal, ActionResult

from .generalizer import ExperienceGeneralizer
from .models import ExperienceEpisode, ExperienceEvidence
from .multistep import (
    DeterministicOrderedReplayExecutor,
    OrderedReplayManifestCompiler,
)
from .promotion import PromotionGate
from .replay import ReplayPlanBuilder
from .trace import ActionTraceRecorder
from .trace_memory import InMemoryActionTracePort


def _episode(index: int) -> ExperienceEpisode:
    return ExperienceEpisode(
        episode_id=f"ordered-smoke-{index}",
        outcome="success",
        summary="two-step replay completed",
        evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:ordered-source:{index}",
                source_type="test_result",
                summary="source episode verified",
                verified=True,
            ),
        ),
        trigger_conditions=("ordered replay",),
        procedure_steps=("tool:prepare", "tool:verify"),
        request_id=f"ordered-request-{index}",
        engine_id="ordered-smoke-engine",
        verification_status="PASS",
    )


def _result(manifest: dict) -> ActionResult:
    return ActionResult(
        tool_id="unused",
        status="EXECUTED",
        goal_satisfied=True,
        completion_evidence={"replay_manifest": manifest},
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-ordered-replay-smoke")
    parser.parse_args(argv)

    episodes = tuple(_episode(index) for index in range(1, 4))
    traces = InMemoryActionTracePort()
    recorder = ActionTraceRecorder()

    for episode in episodes:
        prepare = recorder.record(
            request_id=episode.request_id,
            ordinal=0,
            proposal=ActionProposal("prepare", {}),
            result=_result(
                {
                    "version": 1,
                    "argv": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "Path('state.txt').write_text('READY', encoding='utf-8'); "
                            "print('prepared')"
                        ),
                    ],
                    "stdout_contains": ["prepared"],
                    "file_expectations": [
                        {
                            "path": "state.txt",
                            "must_exist": True,
                            "exact_text": "READY",
                        }
                    ],
                }
            ),
        )
        verify = recorder.record(
            request_id=episode.request_id,
            ordinal=1,
            proposal=ActionProposal("verify", {}),
            result=_result(
                {
                    "version": 1,
                    "argv": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "value=Path('state.txt').read_text(encoding='utf-8'); "
                            "assert value == 'READY'; "
                            "Path('done.txt').write_text('OK', encoding='utf-8'); "
                            "print('verified:' + value)"
                        ),
                    ],
                    "stdout_contains": ["verified:READY"],
                    "file_expectations": [
                        {
                            "path": "done.txt",
                            "must_exist": True,
                            "exact_text": "OK",
                        }
                    ],
                }
            ),
        )
        traces.put_trace(prepare)
        traces.put_trace(verify)

    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)
    sequences = OrderedReplayManifestCompiler().compile(
        plan,
        episodes,
        traces,
    )

    with TemporaryDirectory(prefix="yisang-ordered-root-") as root:
        report = DeterministicOrderedReplayExecutor(
            allowed_executables=(sys.executable,),
            workspace_root=Path(root),
        ).execute(plan, sequences)

    outcome = PromotionGate(min_success_count=3).promote(candidate, report)
    payload = {
        "ready": bool(
            outcome.decision.accepted
            and all(result.passed for result in report.results)
        ),
        "source_episode_count": len(episodes),
        "sequence_count": len(sequences),
        "steps_per_sequence": [len(item.steps) for item in sequences],
        "shared_workspace_proven": all(
            result.passed for result in report.results
        ),
        "fail_fast": True,
        "all_replays_passed": all(
            result.passed for result in report.results
        ),
        "promotion_accepted": outcome.decision.accepted,
        "promotion_reason": outcome.decision.reason,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
