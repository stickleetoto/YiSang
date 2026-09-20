import pytest

from yisang.experience import (
    ExperienceEvidence, ExperienceEpisode, ExperienceGeneralizer,
    ReplayPlanBuilder, ReplayPlanError,
)


def _episodes():
    return tuple(
        ExperienceEpisode(
            episode_id=f"episode-{index}", outcome="success", summary="repair",
            evidence=(ExperienceEvidence(f"test:{index}", "test_result", "verified", True),),
            trigger_conditions=("python test failure",),
            procedure_steps=("tool:pytest", "tool:patch", "tool:pytest"),
        )
        for index in range(3)
    )


def test_replay_plan_maps_each_source_episode():
    episodes = _episodes()
    candidate = ExperienceGeneralizer().generalize(episodes)
    plan = ReplayPlanBuilder().build(candidate, episodes)
    assert plan.candidate_id == candidate.candidate_id
    assert len(plan.cases) == 3
    assert tuple(case.source_episode_id for case in plan.cases) == candidate.source_episode_ids
    assert all(case.required_evidence_refs for case in plan.cases)


def test_replay_report_requires_complete_results():
    episodes = _episodes()
    candidate = ExperienceGeneralizer().generalize(episodes)
    builder = ReplayPlanBuilder()
    plan = builder.build(candidate, episodes)
    with pytest.raises(ReplayPlanError, match="missing replay results"):
        builder.report(plan, {plan.cases[0].test_id: True})


def test_replay_report_preserves_candidate_id_and_order():
    episodes = _episodes()
    candidate = ExperienceGeneralizer().generalize(episodes)
    builder = ReplayPlanBuilder()
    plan = builder.build(candidate, episodes)
    report = builder.report(plan, {case.test_id: True for case in reversed(plan.cases)})
    assert report.candidate_id == candidate.candidate_id
    assert tuple(result.test_id for result in report.results) == tuple(case.test_id for case in plan.cases)
    assert all(result.passed for result in report.results)
