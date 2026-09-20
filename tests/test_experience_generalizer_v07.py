import pytest

from yisang.experience import (
    ExperienceEvidence,
    ExperienceEpisode,
    ExperienceGeneralizationError,
    ExperienceGeneralizer,
)


def _episode(index, *, outcome="success", trigger="python test failure",
             steps=("tool:pytest", "tool:patch", "tool:pytest"), verified=True):
    return ExperienceEpisode(
        episode_id=f"episode-{index}", outcome=outcome, summary="same summary",
        evidence=(ExperienceEvidence(f"test:{index}", "test_result", "verified replay", verified),),
        trigger_conditions=(trigger,), procedure_steps=steps,
    )


def test_generalizes_repeated_verified_procedure():
    episodes = tuple(_episode(index) for index in range(3))
    candidate = ExperienceGeneralizer(min_repeats=3).generalize(episodes)
    assert candidate.kind == "procedure"
    assert candidate.target == "ego_procedure"
    assert candidate.success_count == 3
    assert candidate.failure_count == 0
    assert candidate.trigger_conditions == ("python test failure",)
    assert len(candidate.validation_tests) == 3
    assert len(candidate.source_evidence) == 3
    assert candidate.metadata["repeat_count"] == 3


def test_candidate_id_is_deterministic_across_input_order():
    episodes = tuple(_episode(index) for index in range(3))
    g = ExperienceGeneralizer(min_repeats=3)
    assert g.generalize(episodes).candidate_id == g.generalize(tuple(reversed(episodes))).candidate_id


def test_rejects_insufficient_repeats():
    with pytest.raises(ExperienceGeneralizationError, match="at least 3"):
        ExperienceGeneralizer(min_repeats=3).generalize((_episode(1), _episode(2)))


def test_rejects_episode_without_promotable_evidence():
    episodes = (_episode(1), _episode(2), _episode(3, verified=False))
    with pytest.raises(ExperienceGeneralizationError, match="every source episode"):
        ExperienceGeneralizer().generalize(episodes)


def test_rejects_trigger_mismatch():
    episodes = (_episode(1), _episode(2), _episode(3, trigger="network failure"))
    with pytest.raises(ExperienceGeneralizationError, match="share at least one"):
        ExperienceGeneralizer().generalize(episodes)


def test_rejects_procedure_step_mismatch():
    episodes = (_episode(1), _episode(2), _episode(3, steps=("tool:pytest", "tool:rewrite", "tool:pytest")))
    with pytest.raises(ExperienceGeneralizationError, match="steps differ"):
        ExperienceGeneralizer().generalize(episodes)


def test_generalizes_repeated_failure_as_warning():
    episodes = tuple(_episode(index, outcome="failure", steps=()) for index in range(3))
    candidate = ExperienceGeneralizer().generalize(
        episodes, kind="warning", target="durable_warning"
    )
    assert candidate.failure_count == 3
    assert candidate.success_count == 0
    assert candidate.kind == "warning"
    assert "Repeated failure observed" in candidate.proposed_content
