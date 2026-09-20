from __future__ import annotations

import uuid

from .models import (
    LessonCandidate,
    PromotionArtifact,
    PromotionDecision,
    PromotionOutcome,
    ReplayReport,
)

_ALLOWED_TARGETS_BY_KIND = {
    "procedure": frozenset(
        {"ego_instruction", "ego_procedure", "tool_routing_heuristic"}
    ),
    "knowledge": frozenset({"library_knowledge"}),
    "warning": frozenset({"durable_warning", "library_knowledge"}),
}

_BLOCKED_AUTO_RISKS = frozenset({"privileged", "security_sensitive"})


class PromotionGate:
    """Deterministic v0.7 promotion boundary.

    This gate produces a versioned PromotionArtifact only. It never mutates
    E.G.O, the Roland Library, or another authoritative store by itself.
    """

    def __init__(self, *, min_success_count: int = 1) -> None:
        if min_success_count < 1:
            raise ValueError("min_success_count must be >= 1")
        self._min_success_count = min_success_count

    def evaluate(
        self,
        candidate: LessonCandidate,
        replay: ReplayReport,
    ) -> PromotionDecision:
        if not candidate.source_episode_ids:
            return PromotionDecision(False, "source_episodes_required")

        if not candidate.source_evidence:
            return PromotionDecision(False, "source_evidence_required")

        if not any(item.is_promotable for item in candidate.source_evidence):
            return PromotionDecision(
                False,
                "verified_promotable_evidence_required",
                risk_flags=("raw_or_unverified_evidence_only",),
            )

        if candidate.risk_class in _BLOCKED_AUTO_RISKS:
            return PromotionDecision(
                False,
                "automatic_promotion_blocked_for_risk",
                risk_flags=(candidate.risk_class,),
            )

        allowed_targets = _ALLOWED_TARGETS_BY_KIND[candidate.kind]
        if candidate.target not in allowed_targets:
            return PromotionDecision(
                False,
                "target_not_allowed_for_candidate_kind",
            )

        if not candidate.validation_tests:
            return PromotionDecision(False, "validation_tests_required")

        if replay.candidate_id != candidate.candidate_id:
            return PromotionDecision(False, "replay_candidate_mismatch")

        by_test: dict[str, list[bool]] = {}
        for result in replay.results:
            by_test.setdefault(result.test_id, []).append(result.passed)

        duplicate_tests = tuple(
            sorted(test_id for test_id, values in by_test.items() if len(values) > 1)
        )
        if duplicate_tests:
            return PromotionDecision(
                False,
                "duplicate_replay_results",
                risk_flags=duplicate_tests,
            )

        expected = tuple(dict.fromkeys(candidate.validation_tests))
        missing = tuple(test_id for test_id in expected if test_id not in by_test)
        if missing:
            return PromotionDecision(
                False,
                "replay_incomplete",
                missing_tests=missing,
            )

        failed = tuple(test_id for test_id in expected if not by_test[test_id][0])
        if failed:
            return PromotionDecision(
                False,
                "replay_failed",
                failed_tests=failed,
            )

        if candidate.kind in {"procedure", "knowledge"}:
            if candidate.success_count < self._min_success_count:
                return PromotionDecision(
                    False,
                    "successful_experience_required",
                )

        if candidate.kind == "warning" and candidate.failure_count < 1:
            return PromotionDecision(
                False,
                "failure_evidence_required_for_warning",
            )

        return PromotionDecision(True, "promotion_gate_passed")

    def promote(
        self,
        candidate: LessonCandidate,
        replay: ReplayReport,
    ) -> PromotionOutcome:
        decision = self.evaluate(candidate, replay)
        if not decision.accepted:
            return PromotionOutcome(decision=decision)

        artifact = PromotionArtifact(
            artifact_id=f"promotion-{uuid.uuid4().hex[:12]}",
            candidate_id=candidate.candidate_id,
            kind=candidate.kind,
            target=candidate.target,
            title=candidate.title,
            content=candidate.proposed_content,
            version=candidate.version,
            source_episode_ids=candidate.source_episode_ids,
            evidence_refs=tuple(
                dict.fromkeys(
                    evidence.evidence_ref for evidence in candidate.source_evidence
                )
            ),
            validation_run_id=replay.run_id,
            trigger_conditions=candidate.trigger_conditions,
            scope=candidate.scope,
            risk_class=candidate.risk_class,
        )
        return PromotionOutcome(decision=decision, artifact=artifact)
