from __future__ import annotations

import sys

import pytest

from yisang.execution.models import ActionProposal, ActionResult
from yisang.experience import (
    ActionTraceRecorder,
    ExperienceEvidence,
    ExperienceEpisode,
    ExperienceGeneralizer,
    InMemoryActionTracePort,
    ReplayManifestCompiler,
    ReplayManifestError,
    ReplayPlanBuilder,
    SQLiteActionTracePort,
)


def _episode(index: int) -> ExperienceEpisode:
    return ExperienceEpisode(
        episode_id=f"episode-{index}",
        outcome="success",
        summary="trace replay",
        evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:{index}",
                source_type="test_result",
                summary="verified",
                verified=True,
            ),
        ),
        trigger_conditions=("trace replay",),
        procedure_steps=("tool:python.replay",),
        request_id=f"request-{index}",
    )


def _trace(episode: ExperienceEpisode, ordinal: int = 0):
    return ActionTraceRecorder().record(
        request_id=episode.request_id,
        ordinal=ordinal,
        proposal=ActionProposal("python.replay", {"raw": "private"}),
        result=ActionResult(
            tool_id="python.replay",
            status="EXECUTED",
            goal_satisfied=True,
            completion_evidence={
                "replay_manifest": {
                    "version": 1,
                    "argv": [sys.executable, "-c", "print('ok')"],
                    "stdout_contains": ["ok"],
                }
            },
        ),
    )


def test_sqlite_trace_round_trip(tmp_path) -> None:
    episode = _episode(1)
    trace = _trace(episode)
    db = tmp_path / "traces.db"
    with SQLiteActionTracePort(db) as port:
        port.put_trace(trace)
    with SQLiteActionTracePort(db) as port:
        assert port.get_trace(trace.trace_id) == trace
        assert port.for_request(episode.request_id) == (trace,)


def test_compiler_maps_source_episode_trace_to_each_replay_case() -> None:
    episodes = tuple(_episode(index) for index in range(3))
    traces = InMemoryActionTracePort()
    for episode in episodes:
        traces.put_trace(_trace(episode))
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    specs = ReplayManifestCompiler().compile(plan, episodes, traces)

    assert len(specs) == 3
    assert tuple(spec.test_id for spec in specs) == tuple(
        case.test_id for case in plan.cases
    )
    assert all(spec.argv[0] == sys.executable for spec in specs)


def test_compiler_rejects_missing_trace() -> None:
    episodes = tuple(_episode(index) for index in range(3))
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with pytest.raises(ReplayManifestError, match="no replayable trace"):
        ReplayManifestCompiler().compile(
            plan,
            episodes,
            InMemoryActionTracePort(),
        )


def test_compiler_rejects_ambiguous_matching_trace() -> None:
    episodes = tuple(_episode(index) for index in range(3))
    traces = InMemoryActionTracePort()
    for episode in episodes:
        traces.put_trace(_trace(episode, ordinal=0))
        traces.put_trace(_trace(episode, ordinal=1))
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with pytest.raises(ReplayManifestError, match="ambiguous"):
        ReplayManifestCompiler().compile(plan, episodes, traces)


def test_compiler_rejects_multi_tool_v1_plan() -> None:
    episodes = tuple(
        ExperienceEpisode(
            episode_id=f"multi-{index}",
            outcome="success",
            summary="multi",
            evidence=(
                ExperienceEvidence(
                    evidence_ref=f"test:multi:{index}",
                    source_type="test_result",
                    summary="verified",
                    verified=True,
                ),
            ),
            trigger_conditions=("multi",),
            procedure_steps=("tool:first", "tool:second"),
            request_id=f"multi-request-{index}",
        )
        for index in range(3)
    )
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)

    with pytest.raises(ReplayManifestError, match="exactly one"):
        ReplayManifestCompiler().compile(
            plan,
            episodes,
            InMemoryActionTracePort(),
        )
