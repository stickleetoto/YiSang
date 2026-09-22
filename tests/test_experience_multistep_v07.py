from __future__ import annotations

import sys

import pytest

from yisang.execution.models import ActionProposal, ActionResult
from yisang.experience import (
    ActionTraceRecorder,
    DeterministicOrderedReplayExecutor,
    ExperienceEvidence,
    ExperienceEpisode,
    ExperienceGeneralizer,
    InMemoryActionTracePort,
    OrderedReplayError,
    OrderedReplayManifestCompiler,
    OrderedReplaySequence,
    ReplayExecutionSpec,
    ReplayPlanBuilder,
)


def _episodes():
    return tuple(
        ExperienceEpisode(
            episode_id=f"episode-{index}",
            outcome="success",
            summary="ordered",
            evidence=(
                ExperienceEvidence(
                    evidence_ref=f"test:{index}",
                    source_type="test_result",
                    summary="verified",
                    verified=True,
                ),
            ),
            trigger_conditions=("ordered",),
            procedure_steps=("tool:prepare", "tool:verify"),
            request_id=f"request-{index}",
        )
        for index in range(3)
    )


def _trace(request_id, ordinal, tool_id, code, *, goal_satisfied=True):
    return ActionTraceRecorder().record(
        request_id=request_id,
        ordinal=ordinal,
        proposal=ActionProposal(tool_id, {}),
        result=ActionResult(
            tool_id=tool_id,
            status="EXECUTED",
            goal_satisfied=goal_satisfied,
            completion_evidence={
                "replay_manifest": {
                    "version": 1,
                    "argv": [sys.executable, "-c", code],
                }
            },
        ),
    )


def test_ordered_compiler_preserves_trace_order():
    episodes = _episodes()
    traces = InMemoryActionTracePort()
    for episode in episodes:
        traces.put_trace(
            _trace(episode.request_id, 0, "prepare", "print('prepare')")
        )
        traces.put_trace(
            _trace(episode.request_id, 1, "verify", "print('verify')")
        )
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    sequences = OrderedReplayManifestCompiler().compile(
        plan, episodes, traces
    )

    assert len(sequences) == 3
    assert all(len(sequence.steps) == 2 for sequence in sequences)
    assert all(":step:1:prepare" in sequence.steps[0].test_id for sequence in sequences)
    assert all(":step:2:verify" in sequence.steps[1].test_id for sequence in sequences)


def test_ordered_compiler_rejects_tool_order_mismatch():
    episodes = _episodes()
    traces = InMemoryActionTracePort()
    for episode in episodes:
        traces.put_trace(
            _trace(episode.request_id, 0, "verify", "print('verify')")
        )
        traces.put_trace(
            _trace(episode.request_id, 1, "prepare", "print('prepare')")
        )
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with pytest.raises(OrderedReplayError, match="tool order mismatch"):
        OrderedReplayManifestCompiler().compile(plan, episodes, traces)


def test_ordered_compiler_rejects_unverified_step():
    episodes = _episodes()
    traces = InMemoryActionTracePort()
    for episode in episodes:
        traces.put_trace(
            _trace(episode.request_id, 0, "prepare", "print('prepare')")
        )
        traces.put_trace(
            _trace(
                episode.request_id,
                1,
                "verify",
                "print('verify')",
                goal_satisfied=False,
            )
        )
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with pytest.raises(OrderedReplayError, match="not replayable"):
        OrderedReplayManifestCompiler().compile(plan, episodes, traces)


def test_ordered_executor_shares_workspace_between_steps(tmp_path):
    episodes = _episodes()
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)
    sequences = tuple(
        OrderedReplaySequence(
            test_id=case.test_id,
            steps=(
                ReplayExecutionSpec(
                    test_id=f"{case.test_id}:one",
                    argv=(
                        sys.executable,
                        "-c",
                        "from pathlib import Path; Path('state.txt').write_text('READY')",
                    ),
                ),
                ReplayExecutionSpec(
                    test_id=f"{case.test_id}:two",
                    argv=(
                        sys.executable,
                        "-c",
                        (
                            "from pathlib import Path; "
                            "assert Path('state.txt').read_text() == 'READY'"
                        ),
                    ),
                ),
            ),
        )
        for case in plan.cases
    )

    report = DeterministicOrderedReplayExecutor(
        allowed_executables=(sys.executable,),
        workspace_root=tmp_path,
    ).execute(plan, sequences)

    assert all(result.passed for result in report.results)
    assert all("executed_steps=2" in result.detail for result in report.results)
    assert all(len(result.evidence_refs) == 2 for result in report.results)


def test_ordered_executor_fails_fast(tmp_path):
    episodes = _episodes()
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)
    sequences = tuple(
        OrderedReplaySequence(
            test_id=case.test_id,
            steps=(
                ReplayExecutionSpec(
                    test_id=f"{case.test_id}:fail",
                    argv=(sys.executable, "-c", "raise SystemExit(3)"),
                ),
                ReplayExecutionSpec(
                    test_id=f"{case.test_id}:must-not-run",
                    argv=(sys.executable, "-c", "print('should not run')"),
                ),
            ),
        )
        for case in plan.cases
    )

    report = DeterministicOrderedReplayExecutor(
        allowed_executables=(sys.executable,),
        workspace_root=tmp_path,
    ).execute(plan, sequences)

    assert all(not result.passed for result in report.results)
    assert all("executed_steps=1" in result.detail for result in report.results)
    assert all(len(result.evidence_refs) == 1 for result in report.results)
