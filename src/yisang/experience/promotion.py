from __future__ import annotations

from dataclasses import replace
import time

from yisang.library.models import LibraryUsageNote
from yisang.library.port import LibraryPort

from .models import (
    ExperienceCandidate,
    ExperienceObservation,
    ExperiencePromotionResult,
)
from .port import ExperiencePort


class ExperiencePromotionEngine:
    """Aggregate verified experience and promote only gated reusable lessons."""

    def __init__(
        self,
        *,
        experience: ExperiencePort,
        library: LibraryPort,
        min_successes: int = 3,
    ) -> None:
        if min_successes < 1:
            raise ValueError("min_successes must be >= 1")
        self.experience = experience
        self.library = library
        self.min_successes = min_successes

    def observe(
        self,
        observation: ExperienceObservation,
    ) -> ExperiencePromotionResult:
        if not observation.verified:
            return ExperiencePromotionResult(
                status="rejected",
                reason="unverified_observation",
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

        promoted, reinforced = promotion
        candidate = replace(candidate, status="promoted")
        self.experience.put(candidate)
        return ExperiencePromotionResult(
            status="promoted",
            reason="verified_distinct_success_threshold_met",
            candidate=candidate,
            promoted=promoted,
            reinforced=reinforced,
        )

    def _promote_usage_note(
        self,
        candidate: ExperienceCandidate,
    ) -> tuple[bool, bool] | None:
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
        return promoted, reinforced


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
