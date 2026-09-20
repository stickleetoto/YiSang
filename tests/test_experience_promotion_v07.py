import pytest

from yisang.experience import (
    ExperienceEvidence,
    InMemoryPromotionLedger,
    LessonCandidate,
    PromotionGate,
    ReplayCaseResult,
    ReplayReport,
)


def _evidence(
    source_type: str = "test_result",
    *,
    verified: bool = True,
    ref: str = "evidence:test:1",
) -> ExperienceEvidence:
    return ExperienceEvidence(
        evidence_ref=ref,
        source_type=source_type,
        summary="verified outcome evidence",
        verified=verified,
    )


def _candidate(**overrides) -> LessonCandidate:
    values = {
        "candidate_id": "candidate-1",
        "kind": "procedure",
        "target": "ego_procedure",
        "title": "Use exact-path verification after writes",
        "proposed_content": "After a file write, verify the requested path exists.",
        "source_episode_ids": ("episode-1",),
        "source_evidence": (_evidence(),),
        "trigger_conditions": ("file write requested",),
        "validation_tests": ("replay-write", "replay-existing-file"),
        "success_count": 2,
        "failure_count": 0,
        "scope": "filesystem",
        "risk_class": "normal",
        "version": "1",
    }
    values.update(overrides)
    return LessonCandidate(**values)


def _replay(
    *,
    candidate_id: str = "candidate-1",
    first_passed: bool = True,
    include_second: bool = True,
) -> ReplayReport:
    results = [
        ReplayCaseResult(
            test_id="replay-write",
            passed=first_passed,
            evidence_refs=("run:write:1",),
        )
    ]
    if include_second:
        results.append(
            ReplayCaseResult(
                test_id="replay-existing-file",
                passed=True,
                evidence_refs=("run:existing:1",),
            )
        )
    return ReplayReport(candidate_id=candidate_id, results=tuple(results))


def test_raw_conversation_only_cannot_be_promoted() -> None:
    candidate = _candidate(
        source_evidence=(
            _evidence(
                "raw_conversation",
                verified=True,
                ref="conversation:raw:1",
            ),
        )
    )

    decision = PromotionGate().evaluate(candidate, _replay())

    assert decision.accepted is False
    assert decision.reason == "verified_promotable_evidence_required"


@pytest.mark.parametrize("risk_class", ["privileged", "security_sensitive"])
def test_sensitive_capability_is_not_auto_promoted(risk_class: str) -> None:
    candidate = _candidate(risk_class=risk_class)

    decision = PromotionGate().evaluate(candidate, _replay())

    assert decision.accepted is False
    assert decision.reason == "automatic_promotion_blocked_for_risk"
    assert risk_class in decision.risk_flags


def test_replay_must_cover_every_declared_validation_test() -> None:
    decision = PromotionGate().evaluate(
        _candidate(),
        _replay(include_second=False),
    )

    assert decision.accepted is False
    assert decision.reason == "replay_incomplete"
    assert decision.missing_tests == ("replay-existing-file",)


def test_failed_replay_blocks_promotion() -> None:
    decision = PromotionGate().evaluate(
        _candidate(),
        _replay(first_passed=False),
    )

    assert decision.accepted is False
    assert decision.reason == "replay_failed"
    assert decision.failed_tests == ("replay-write",)


def test_replay_for_another_candidate_is_rejected() -> None:
    decision = PromotionGate().evaluate(
        _candidate(),
        _replay(candidate_id="candidate-other"),
    )

    assert decision.accepted is False
    assert decision.reason == "replay_candidate_mismatch"


def test_validated_procedure_produces_artifact_without_direct_side_effect() -> None:
    outcome = PromotionGate().promote(_candidate(), _replay())

    assert outcome.decision.accepted is True
    assert outcome.artifact is not None
    assert outcome.artifact.target == "ego_procedure"
    assert outcome.artifact.version == "1"
    assert outcome.artifact.evidence_refs == ("evidence:test:1",)
    assert outcome.artifact.active is True


def test_warning_requires_failure_evidence() -> None:
    candidate = _candidate(
        kind="warning",
        target="durable_warning",
        success_count=0,
        failure_count=0,
    )

    decision = PromotionGate().evaluate(candidate, _replay())

    assert decision.accepted is False
    assert decision.reason == "failure_evidence_required_for_warning"


def test_validated_failure_can_be_promoted_as_warning() -> None:
    candidate = _candidate(
        kind="warning",
        target="durable_warning",
        success_count=0,
        failure_count=2,
        proposed_content="Do not retry an irreversible side effect after verified success.",
    )

    outcome = PromotionGate().promote(candidate, _replay())

    assert outcome.decision.accepted is True
    assert outcome.artifact is not None
    assert outcome.artifact.kind == "warning"


def test_promotion_artifact_can_be_invalidated_and_remains_inspectable() -> None:
    outcome = PromotionGate().promote(_candidate(), _replay())
    assert outcome.artifact is not None

    ledger = InMemoryPromotionLedger()
    ledger.add(outcome.artifact)
    invalidated = ledger.invalidate(
        outcome.artifact.artifact_id,
        reason="new replay disproved the procedure",
    )

    assert invalidated.active is False
    assert invalidated.invalidation_reason == "new replay disproved the procedure"
    assert ledger.list_active() == ()
    assert ledger.get(outcome.artifact.artifact_id) is invalidated


def test_candidate_kind_cannot_write_to_unrelated_target() -> None:
    candidate = _candidate(
        kind="knowledge",
        target="ego_procedure",
    )

    decision = PromotionGate().evaluate(candidate, _replay())

    assert decision.accepted is False
    assert decision.reason == "target_not_allowed_for_candidate_kind"
