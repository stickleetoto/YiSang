from dataclasses import replace

import pytest

from yisang.experience import (
    CallableReplayAdapter,
    EpisodeRecord,
    EpisodeStep,
    ExperienceObservation,
    ExperiencePromotionEngine,
    InMemoryExperiencePort,
    ReplayCheck,
    ReplayCheckResult,
    ReplayValidationResult,
    ReplayValidator,
    SQLiteEpisodePort,
    observation_from_replay,
)
from yisang.library.in_memory import InMemoryLibraryPort
from yisang.library.models import Book, KnowledgeEntry


def _episode(*, episode_id: str = "ep-1", outcome: str = "success"):
    return EpisodeRecord(
        episode_id=episode_id,
        request_id="req-1",
        goal="fix failing tests",
        outcome=outcome,
        steps=(
            EpisodeStep(
                step_id="step-1",
                kind="tool",
                status="EXECUTED",
                action="pytest",
                evidence_refs=("run:original",),
            ),
        ),
        verification_refs=("verify:original",),
        created_at=123.0,
    )


def _library() -> InMemoryLibraryPort:
    return InMemoryLibraryPort(
        (
            Book(
                book_id="book.python",
                title="Python Core",
                version="1",
                entries=(
                    KnowledgeEntry(
                        entry_id="pytest-debug",
                        title="Debug pytest failures",
                        summary="Use causal evidence before broad edits.",
                    ),
                ),
            ),
        )
    )


def _pass_runner(check: ReplayCheck, episode: EpisodeRecord):
    return ReplayCheckResult(
        check_id=check.check_id,
        status="PASS",
        evidence_refs=(f"artifact:{episode.episode_id}:{check.check_id}",),
        details={"kind": check.kind},
    )


def test_episode_fingerprint_is_stable_across_serialization():
    episode = _episode()
    restored = EpisodeRecord.from_dict(episode.to_dict())

    assert restored == episode
    assert restored.fingerprint() == episode.fingerprint()


def test_sqlite_episode_store_survives_restart_and_checks_integrity(tmp_path):
    path = tmp_path / "episodes.db"
    episode = _episode()

    SQLiteEpisodePort(path).put(episode)
    restored = SQLiteEpisodePort(path).get("ep-1")

    assert restored == episode
    assert restored.fingerprint() == episode.fingerprint()


def test_sqlite_episode_store_rejects_same_id_with_different_content(tmp_path):
    path = tmp_path / "episodes.db"
    store = SQLiteEpisodePort(path)
    store.put(_episode())

    with pytest.raises(ValueError, match="episode_id collision"):
        store.put(replace(_episode(), goal="different goal"))


def test_replay_validator_creates_deterministic_verification_reference():
    episode = _episode()
    checks = (
        ReplayCheck("unit", "pytest", {"target": "tests/unit"}),
        ReplayCheck("smoke", "build", {"target": "package"}),
    )
    validator = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner),
    )

    first = validator.validate(episode, checks)
    second = validator.validate(episode, checks)

    assert first.accepted is True
    assert first.reason == "replay_verified"
    assert first.verification_ref is not None
    assert first.verification_ref.startswith("replay:")
    assert first.verification_ref == second.verification_ref


def test_replay_validator_fails_closed_on_required_failure():
    def runner(check, episode):
        return ReplayCheckResult(
            check_id=check.check_id,
            status="FAIL",
            evidence_refs=("artifact:failure",),
        )

    result = ReplayValidator(
        adapter=CallableReplayAdapter(runner)
    ).validate(
        _episode(),
        (ReplayCheck("unit", "pytest"),),
    )

    assert result.accepted is False
    assert result.reason == "required_replay_check_fail"
    assert result.verification_ref is None


def test_replay_validator_requires_evidence_for_required_pass():
    def runner(check, episode):
        return ReplayCheckResult(
            check_id=check.check_id,
            status="PASS",
        )

    result = ReplayValidator(
        adapter=CallableReplayAdapter(runner)
    ).validate(
        _episode(),
        (ReplayCheck("unit", "pytest"),),
    )

    assert result.accepted is False
    assert result.reason == "required_replay_check_missing_evidence"


def test_replay_validator_converts_adapter_exception_to_fail_closed_error():
    def runner(check, episode):
        raise RuntimeError("runner exploded")

    result = ReplayValidator(
        adapter=CallableReplayAdapter(runner)
    ).validate(
        _episode(),
        (ReplayCheck("unit", "pytest"),),
    )

    assert result.accepted is False
    assert result.reason == "required_replay_check_error"
    assert result.check_results[0].details["error_type"] == "RuntimeError"


def test_unsuccessful_source_episode_cannot_be_replay_verified():
    result = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner)
    ).validate(
        _episode(outcome="failure"),
        (ReplayCheck("unit", "pytest"),),
    )

    assert result.accepted is False
    assert result.reason == "source_episode_not_successful"


def test_replay_bridge_builds_verified_observation_bound_to_episode():
    episode = _episode()
    replay = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner)
    ).validate(
        episode,
        (ReplayCheck("unit", "pytest"),),
    )

    observation = observation_from_replay(
        episode=episode,
        replay=replay,
        target_book_id="book.python",
        target_entry_id="pytest-debug",
        lesson="Run the narrow failing test before broad edits.",
        applies_when=("pytest fails",),
    )

    assert observation.verified is True
    assert observation.validation_method == "replay"
    assert observation.verification_ref == replay.verification_ref
    assert observation.source_episode_id == episode.episode_id
    assert observation.evidence_id.startswith("replay_ev_")


def test_replay_bridge_rejects_result_from_different_episode():
    source = _episode(episode_id="ep-source")
    target = _episode(episode_id="ep-target")
    replay = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner)
    ).validate(
        source,
        (ReplayCheck("unit", "pytest"),),
    )

    with pytest.raises(ValueError, match="does not match episode"):
        observation_from_replay(
            episode=target,
            replay=replay,
            target_book_id="book.python",
            target_entry_id="pytest-debug",
            lesson="Do not cross-bind replay evidence.",
        )


def test_replay_required_promotion_rejects_external_assertion():
    engine = ExperiencePromotionEngine(
        experience=InMemoryExperiencePort(),
        library=_library(),
        min_successes=1,
        require_replay=True,
    )

    result = engine.observe(
        ExperienceObservation(
            evidence_id="external-1",
            target_book_id="book.python",
            target_entry_id="pytest-debug",
            lesson="Externally asserted lesson.",
            verified=True,
            verification_ref="manual:claim",
        )
    )

    assert result.status == "rejected"
    assert result.reason == "replay_verification_required"


def test_replay_verified_observation_can_cross_strict_promotion_gate():
    episode = _episode()
    replay = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner)
    ).validate(
        episode,
        (ReplayCheck("unit", "pytest"),),
    )
    observation = observation_from_replay(
        episode=episode,
        replay=replay,
        target_book_id="book.python",
        target_entry_id="pytest-debug",
        lesson="Run the narrow failing test before broad edits.",
    )

    library = _library()
    engine = ExperiencePromotionEngine(
        experience=InMemoryExperiencePort(),
        library=library,
        min_successes=1,
        require_replay=True,
    )
    result = engine.observe(observation)

    assert result.status == "promoted"
    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert entry.usage_notes[0].verification[0].startswith("replay:")


def test_same_replay_episode_cannot_count_twice():
    episode = _episode()
    replay = ReplayValidator(
        adapter=CallableReplayAdapter(_pass_runner)
    ).validate(
        episode,
        (ReplayCheck("unit", "pytest"),),
    )
    observation = observation_from_replay(
        episode=episode,
        replay=replay,
        target_book_id="book.python",
        target_entry_id="pytest-debug",
        lesson="Run the narrow failing test before broad edits.",
    )

    engine = ExperiencePromotionEngine(
        experience=InMemoryExperiencePort(),
        library=_library(),
        min_successes=2,
        require_replay=True,
    )

    first = engine.observe(observation)
    duplicate = engine.observe(observation)

    assert first.status == "recorded"
    assert duplicate.status == "duplicate"
    assert duplicate.candidate is not None
    assert duplicate.candidate.success_count == 1


def test_fabricated_replay_result_cannot_cross_episode_binding():
    episode = _episode()
    fabricated = ReplayValidationResult(
        accepted=True,
        reason="replay_verified",
        episode_fingerprint="0" * 64,
        verification_ref="replay:" + "1" * 64,
    )

    with pytest.raises(ValueError, match="does not match episode"):
        observation_from_replay(
            episode=episode,
            replay=fabricated,
            target_book_id="book.python",
            target_entry_id="pytest-debug",
            lesson="Fabricated evidence.",
        )
