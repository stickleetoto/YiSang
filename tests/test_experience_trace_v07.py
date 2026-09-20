from __future__ import annotations

import sys

from yisang.execution.models import ActionProposal, ActionResult
from yisang.experience import ActionTraceRecorder, ReplayExecutionTemplate


def _manifest():
    return {
        "version": 1,
        "argv": [sys.executable, "-c", "print('ok')"],
        "expected_exit_code": 0,
        "stdout_contains": ["ok"],
    }


def test_trace_hashes_arguments_without_storing_raw_values() -> None:
    trace = ActionTraceRecorder().record(
        request_id="req-1",
        ordinal=0,
        proposal=ActionProposal("python.replay", {"secret": "DO_NOT_STORE"}),
        result=ActionResult(
            tool_id="python.replay",
            status="EXECUTED",
            goal_satisfied=True,
            completion_evidence={"replay_manifest": _manifest()},
        ),
    )
    assert trace.replayable is True
    assert trace.replay_template is not None
    assert "DO_NOT_STORE" not in repr(trace)
    assert len(trace.arguments_sha256) == 64


def test_unverified_action_manifest_is_not_replayable() -> None:
    trace = ActionTraceRecorder().record(
        request_id="req-2",
        ordinal=0,
        proposal=ActionProposal("python.replay"),
        result=ActionResult(
            tool_id="python.replay",
            status="EXECUTED",
            goal_satisfied=False,
            completion_evidence={"replay_manifest": _manifest()},
        ),
    )
    assert trace.replayable is False
    assert trace.manifest_rejection_reason == "action_not_verified_for_replay"


def test_invalid_manifest_is_recorded_as_rejected_not_raised() -> None:
    trace = ActionTraceRecorder().record(
        request_id="req-3",
        ordinal=0,
        proposal=ActionProposal("python.replay"),
        result=ActionResult(
            tool_id="python.replay",
            status="EXECUTED",
            goal_satisfied=True,
            completion_evidence={
                "replay_manifest": {
                    "version": 1,
                    "argv": [sys.executable],
                    "shell": True,
                }
            },
        ),
    )
    assert trace.replayable is False
    assert trace.manifest_rejection_reason is not None
    assert "unknown replay manifest fields" in trace.manifest_rejection_reason


def test_execution_template_round_trip_dict() -> None:
    template = ReplayExecutionTemplate.from_dict(_manifest())
    assert ReplayExecutionTemplate.from_dict(template.to_dict()) == template
