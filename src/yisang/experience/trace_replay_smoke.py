from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

from yisang.execution.models import ActionProposal, ActionResult

from .executor import DeterministicReplayExecutor
from .generalizer import ExperienceGeneralizer
from .models import ExperienceEpisode, ExperienceEvidence
from .promotion import PromotionGate
from .replay import ReplayPlanBuilder
from .trace import ActionTraceRecorder, ReplayManifestCompiler
from .trace_memory import InMemoryActionTracePort


def _episode(index: int) -> ExperienceEpisode:
    return ExperienceEpisode(
        episode_id=f"trace-smoke-{index}",
        outcome="success",
        summary="runtime trace produced a replay manifest",
        evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:trace-source:{index}",
                source_type="test_result",
                summary="source episode independently verified",
                verified=True,
            ),
        ),
        trigger_conditions=("trace replay",),
        procedure_steps=("tool:python.replay",),
        request_id=f"trace-request-{index}",
        engine_id="trace-smoke-engine",
        verification_status="PASS",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-trace-replay-smoke")
    parser.parse_args(argv)

    episodes = tuple(_episode(index) for index in range(1, 4))
    traces = InMemoryActionTracePort()
    recorder = ActionTraceRecorder()
    for index, episode in enumerate(episodes, 1):
        proposal = ActionProposal(
            "python.replay",
            {"private_value": f"not-persisted-{index}"},
        )
        result = ActionResult(
            tool_id="python.replay",
            status="EXECUTED",
            goal_satisfied=True,
            completion_evidence={
                "replay_manifest": {
                    "version": 1,
                    "argv": [
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "Path('result.txt').write_text("
                            "'TRACE_REPLAY_OK', encoding='utf-8'); "
                            "print('trace-replay-ok')"
                        ),
                    ],
                    "expected_exit_code": 0,
                    "stdout_contains": ["trace-replay-ok"],
                    "file_expectations": [
                        {
                            "path": "result.txt",
                            "must_exist": True,
                            "exact_text": "TRACE_REPLAY_OK",
                        }
                    ],
                    "timeout_seconds": 10,
                }
            },
        )
        traces.put_trace(
            recorder.record(
                request_id=episode.request_id,
                ordinal=0,
                proposal=proposal,
                result=result,
            )
        )

    candidate = ExperienceGeneralizer().generalize(
        episodes,
        kind="procedure",
        target="ego_procedure",
        scope="coding",
    )
    plan = ReplayPlanBuilder().build(candidate, episodes)
    specs = ReplayManifestCompiler().compile(plan, episodes, traces)

    with TemporaryDirectory(prefix="yisang-trace-replay-root-") as root:
        report = DeterministicReplayExecutor(
            allowed_executables=(sys.executable,),
            workspace_root=Path(root),
        ).execute(plan, specs)

    outcome = PromotionGate(min_success_count=3).promote(candidate, report)
    raw_argument_leaked = any(
        "not-persisted-" in repr(trace)
        for trace in traces.all_traces()
    )
    payload = {
        "ready": bool(
            outcome.decision.accepted
            and all(result.passed for result in report.results)
            and not raw_argument_leaked
        ),
        "source_episode_count": len(episodes),
        "recorded_trace_count": len(traces.all_traces()),
        "compiled_manifest_count": len(specs),
        "executed_replay_count": len(report.results),
        "all_replays_passed": all(
            result.passed for result in report.results
        ),
        "raw_action_arguments_stored": raw_argument_leaked,
        "promotion_accepted": outcome.decision.accepted,
        "promotion_reason": outcome.decision.reason,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
