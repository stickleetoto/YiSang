from __future__ import annotations

from dataclasses import replace
import time

from yisang.library.models import LibraryUsageNote
from yisang.library.port import LibraryPort

from .audit import (
    InMemoryPromotionAuditPort,
    PromotionAuditPort,
    PromotionRevokeResult,
    new_promotion_mutation,
)
from .models import (
    ExperienceCandidate,
    ExperienceObservation,
    ExperiencePromotionResult,
)
from .port import ExperiencePort


class ExperiencePromotionEngine:
    """Aggregate verified experience and govern reversible Library promotion."""

    def __init__(
        self,
        *,
        experience: ExperiencePort,
        library: LibraryPort,
        min_successes: int = 3,
        require_replay: bool = False,
        audit_port: PromotionAuditPort | None = None,
        actor: str = "experience-promotion-engine",
    ) -> None:
        if min_successes < 1:
            raise ValueError("min_successes must be >= 1")
        if not actor.strip():
            raise ValueError("actor must be non-empty")
        self.experience = experience
        self.library = library
        self.min_successes = min_successes
        self.require_replay = require_replay
        self.audit_port = audit_port or InMemoryPromotionAuditPort()
        self.actor = actor

    def observe(
        self,
        observation: ExperienceObservation,
    ) -> ExperiencePromotionResult:
        if not observation.verified:
            return ExperiencePromotionResult(
                status="rejected",
                reason="unverified_observation",
            )
        if self.require_replay:
            if observation.validation_method != "replay":
                return ExperiencePromotionResult(
                    status="rejected",
                    reason="replay_verification_required",
                )
            if not (observation.verification_ref or "").startswith("replay:"):
                return ExperiencePromotionResult(
                    status="rejected",
                    reason="invalid_replay_verification_ref",
                )
            if not (observation.source_episode_id or "").strip():
                return ExperiencePromotionResult(
                    status="rejected",
                    reason="missing_source_episode",
                )

        existing = self.experience.get(observation.candidate_key)
        if existing is None:
            candidate = ExperienceCandidate(
                candidate_key=observation.candidate_key,
                target_book_id=observation.target_book_id,
                target_entry_id=observation.target_entry_id,
                lesson=observation.lesson.strip(),
                applies_when=tuple(observation.applies_when),
                risk_class=observation.risk_class,
            )
        else:
            candidate = existing

        if candidate.status == "revoked":
            return ExperiencePromotionResult(
                status="blocked",
                reason="candidate_revoked",
                candidate=candidate,
            )

        if observation.evidence_id in candidate.evidence_ids:
            return ExperiencePromotionResult(
                status="duplicate",
                reason="duplicate_evidence",
                candidate=candidate,
            )

        if candidate.risk_class != observation.risk_class:
            candidate = replace(
                candidate,
                risk_class=_stricter_risk(
                    candidate.risk_class,
                    observation.risk_class,
                ),
            )

        candidate = replace(
            candidate,
            evidence_ids=(
                *candidate.evidence_ids,
                observation.evidence_id,
            ),
            verification_refs=_append_unique(
                candidate.verification_refs,
                observation.verification_ref,
            ),
            source_episode_ids=_append_unique(
                candidate.source_episode_ids,
                observation.source_episode_id,
            ),
            success_count=(
                candidate.success_count
                + int(observation.outcome == "success")
            ),
            failure_count=(
                candidate.failure_count
                + int(observation.outcome == "failure")
            ),
            updated_at=time.time(),
        )

        if candidate.risk_class != "normal":
            candidate = replace(candidate, status="blocked")
            self.experience.put(candidate)
            return ExperiencePromotionResult(
                status="blocked",
                reason="automatic_promotion_forbidden_for_risk_class",
                candidate=candidate,
            )

        if candidate.failure_count:
            candidate = replace(candidate, status="needs_review")
            self.experience.put(candidate)
            return ExperiencePromotionResult(
                status="needs_review",
                reason="failure_evidence_present",
                candidate=candidate,
            )

        if candidate.success_count < self.min_successes:
            candidate = replace(candidate, status="candidate")
            self.experience.put(candidate)
            return ExperiencePromotionResult(
                status="recorded",
                reason="promotion_threshold_not_met",
                candidate=candidate,
            )

        promotion = self._promote_usage_note(candidate)
        if promotion is None:
            candidate = replace(candidate, status="blocked")
            self.experience.put(candidate)
            return ExperiencePromotionResult(
                status="blocked",
                reason="target_knowledge_not_found",
                candidate=candidate,
            )

        promoted, reinforced, before_note, after_note = promotion
        previous_candidate = candidate
        promoted_candidate = replace(
            candidate,
            status="promoted",
            updated_at=time.time(),
        )
        self.experience.put(promoted_candidate)

        mutation = new_promotion_mutation(
            candidate_key=candidate.candidate_key,
            target_book_id=candidate.target_book_id,
            target_entry_id=candidate.target_entry_id,
            operation="promote" if promoted else "reinforce",
            actor=self.actor,
            reason="verified_distinct_success_threshold_met",
            before_note=before_note,
            after_note=after_note,
            evidence_ids=candidate.evidence_ids,
            verification_refs=candidate.verification_refs,
            source_episode_ids=candidate.source_episode_ids,
        )
        try:
            self.audit_port.append(mutation)
        except Exception:
            self._restore_usage_note(
                candidate,
                expected_current=after_note,
                replacement=before_note,
            )
            self.experience.put(previous_candidate)
            raise

        return ExperiencePromotionResult(
            status="promoted",
            reason="verified_distinct_success_threshold_met",
            candidate=promoted_candidate,
            promoted=promoted,
            reinforced=reinforced,
        )

    def revoke(
        self,
        candidate_key: str,
        *,
        actor: str,
        reason: str,
    ) -> PromotionRevokeResult:
        if not actor.strip():
            raise ValueError("actor must be non-empty")
        if not reason.strip():
            raise ValueError("reason must be non-empty")

        candidate = self.experience.get(candidate_key)
        if candidate is None:
            return PromotionRevokeResult(
                status="not_found",
                reason="candidate_not_found",
                candidate_key=candidate_key,
            )
        if candidate.status == "revoked":
            return PromotionRevokeResult(
                status="already_revoked",
                reason="candidate_already_revoked",
                candidate_key=candidate_key,
            )
        if candidate.status != "promoted":
            return PromotionRevokeResult(
                status="not_promoted",
                reason="candidate_is_not_promoted",
                candidate_key=candidate_key,
            )

        applied = tuple(
            item
            for item in self.audit_port.for_candidate(candidate_key)
            if item.operation in {"promote", "reinforce"}
        )
        if not applied:
            return PromotionRevokeResult(
                status="blocked",
                reason="missing_promotion_audit",
                candidate_key=candidate_key,
            )

        first = applied[0]
        latest = applied[-1]
        if latest.after_note is None:
            return PromotionRevokeResult(
                status="blocked",
                reason="invalid_promotion_audit",
                candidate_key=candidate_key,
            )

        restored = self._restore_usage_note(
            candidate,
            expected_current=latest.after_note,
            replacement=first.before_note,
        )
        if not restored:
            return PromotionRevokeResult(
                status="conflict",
                reason="current_usage_note_diverged",
                candidate_key=candidate_key,
            )

        previous_candidate = candidate
        revoked_candidate = replace(
            candidate,
            status="revoked",
            updated_at=time.time(),
        )
        self.experience.put(revoked_candidate)

        mutation = new_promotion_mutation(
            candidate_key=candidate.candidate_key,
            target_book_id=candidate.target_book_id,
            target_entry_id=candidate.target_entry_id,
            operation="revoke",
            actor=actor,
            reason=reason,
            before_note=latest.after_note,
            after_note=first.before_note,
            evidence_ids=candidate.evidence_ids,
            verification_refs=candidate.verification_refs,
            source_episode_ids=candidate.source_episode_ids,
            metadata={
                "reverted_mutation_ids": [
                    item.mutation_id for item in applied
                ],
            },
        )
        try:
            self.audit_port.append(mutation)
        except Exception:
            self._restore_usage_note(
                candidate,
                expected_current=first.before_note,
                replacement=latest.after_note,
            )
            self.experience.put(previous_candidate)
            raise

        return PromotionRevokeResult(
            status="revoked",
            reason="promotion_revoked",
            candidate_key=candidate_key,
            mutation=mutation,
        )

    def _promote_usage_note(
        self,
        candidate: ExperienceCandidate,
    ) -> tuple[
        bool,
        bool,
        dict | None,
        dict,
    ] | None:
        book = self.library.get_book(candidate.target_book_id)
        if book is None:
            return None

        entry = next(
            (
                item
                for item in book.entries
                if item.entry_id == candidate.target_entry_id
            ),
            None,
        )
        if entry is None:
            return None

        matching_index = next(
            (
                index
                for index, note in enumerate(entry.usage_notes)
                if _same_usage_note(note, candidate)
            ),
            None,
        )

        notes = list(entry.usage_notes)
        promoted = matching_index is None
        reinforced = matching_index is not None
        before_note = (
            None
            if matching_index is None
            else notes[matching_index].to_dict()
        )

        if matching_index is None:
            note = LibraryUsageNote(
                note=candidate.lesson,
                applies_when=tuple(candidate.applies_when),
                successful_uses=candidate.success_count,
                verification=tuple(candidate.verification_refs),
            )
            notes.append(note)
        else:
            previous = notes[matching_index]
            note = LibraryUsageNote(
                note=candidate.lesson,
                applies_when=tuple(candidate.applies_when),
                successful_uses=max(
                    previous.successful_uses,
                    candidate.success_count,
                ),
                verification=tuple(
                    dict.fromkeys(
                        (
                            *previous.verification,
                            *candidate.verification_refs,
                        )
                    )
                ),
            )
            notes[matching_index] = note

        updated_entry = replace(entry, usage_notes=tuple(notes))
        updated_book = replace(
            book,
            entries=tuple(
                updated_entry if item.entry_id == entry.entry_id else item
                for item in book.entries
            ),
        )
        self.library.put_book(updated_book)
        return promoted, reinforced, before_note, note.to_dict()

    def _restore_usage_note(
        self,
        candidate: ExperienceCandidate,
        *,
        expected_current: dict | None,
        replacement: dict | None,
    ) -> bool:
        book = self.library.get_book(candidate.target_book_id)
        if book is None:
            return False
        entry = next(
            (
                item
                for item in book.entries
                if item.entry_id == candidate.target_entry_id
            ),
            None,
        )
        if entry is None:
            return False

        index = next(
            (
                item_index
                for item_index, note in enumerate(entry.usage_notes)
                if _same_usage_note(note, candidate)
            ),
            None,
        )
        current = (
            entry.usage_notes[index].to_dict()
            if index is not None
            else None
        )
        if current != expected_current:
            return False

        notes = list(entry.usage_notes)
        if replacement is None:
            if index is not None:
                notes.pop(index)
        else:
            restored_note = LibraryUsageNote.from_dict(replacement)
            if index is None:
                notes.append(restored_note)
            else:
                notes[index] = restored_note

        updated_entry = replace(entry, usage_notes=tuple(notes))
        self.library.put_book(
            replace(
                book,
                entries=tuple(
                    updated_entry
                    if item.entry_id == entry.entry_id
                    else item
                    for item in book.entries
                ),
            )
        )
        return True


def _same_usage_note(
    note: LibraryUsageNote,
    candidate: ExperienceCandidate,
) -> bool:
    return (
        " ".join(note.note.split()) == " ".join(candidate.lesson.split())
        and tuple(note.applies_when) == tuple(candidate.applies_when)
    )


def _append_unique(
    values: tuple[str, ...],
    value: str | None,
) -> tuple[str, ...]:
    normalized = (value or "").strip()
    if not normalized or normalized in values:
        return values
    return (*values, normalized)


def _stricter_risk(left: str, right: str) -> str:
    order = {
        "normal": 0,
        "privileged": 1,
        "security_sensitive": 2,
    }
    return max((left, right), key=order.__getitem__)


# Backward-compatible import path for E.G.O v2 and pre-consolidation callers.
# The authoritative learning path remains ExperiencePromotionEngine.
from .legacy_promotion import PromotionGate
