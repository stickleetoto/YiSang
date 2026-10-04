from __future__ import annotations

from hashlib import sha256

from .episode import EpisodeRecord
from .models import ExperienceObservation
from .replay import ReplayValidationResult


def observation_from_replay(
    *,
    episode: EpisodeRecord,
    replay: ReplayValidationResult,
    target_book_id: str,
    target_entry_id: str,
    lesson: str,
    applies_when: tuple[str, ...] = (),
    risk_class: str = "normal",
) -> ExperienceObservation:
    if not replay.accepted or not replay.verification_ref:
        raise ValueError("replay result must be accepted")
    if replay.episode_fingerprint != episode.fingerprint():
        raise ValueError("replay result does not match episode")

    evidence_seed = (
        f"{episode.episode_id}\0"
        f"{replay.verification_ref}\0"
        f"{target_book_id}\0"
        f"{target_entry_id}\0"
        f"{' '.join(lesson.split())}"
    ).encode("utf-8")
    evidence_id = f"replay_ev_{sha256(evidence_seed).hexdigest()[:20]}"

    return ExperienceObservation(
        evidence_id=evidence_id,
        target_book_id=target_book_id,
        target_entry_id=target_entry_id,
        lesson=lesson,
        applies_when=applies_when,
        outcome="success",
        verified=True,
        verification_ref=replay.verification_ref,
        validation_method="replay",
        risk_class=risk_class,
        source_episode_id=episode.episode_id,
        metadata={
            "episode_fingerprint": episode.fingerprint(),
            "replay_reason": replay.reason,
            "replay_check_count": len(replay.check_results),
        },
    )
