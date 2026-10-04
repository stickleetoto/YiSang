from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from hashlib import sha256
import json
from typing import Any, Callable

from .episode import EpisodeRecord

REPLAY_STATUSES = frozenset({"PASS", "FAIL", "ERROR", "SKIPPED"})


@dataclass(frozen=True)
class ReplayCheck:
    check_id: str
    kind: str
    payload: dict[str, Any] = field(default_factory=dict)
    required: bool = True

    def __post_init__(self) -> None:
        if not self.check_id.strip():
            raise ValueError("check_id must be non-empty")
        if not self.kind.strip():
            raise ValueError("kind must be non-empty")


@dataclass(frozen=True)
class ReplayCheckResult:
    check_id: str
    status: str
    evidence_refs: tuple[str, ...] = ()
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.check_id.strip():
            raise ValueError("check_id must be non-empty")
        if self.status not in REPLAY_STATUSES:
            raise ValueError(f"unsupported replay status: {self.status}")


@dataclass(frozen=True)
class ReplayValidationResult:
    accepted: bool
    reason: str
    episode_fingerprint: str
    verification_ref: str | None = None
    check_results: tuple[ReplayCheckResult, ...] = ()


class ReplayAdapter(ABC):
    """Execution boundary for reproducibility checks.

    YiSang core describes checks. The adapter decides how to perform them.
    Shell/build/test execution therefore stays outside the promotion core.
    """

    @abstractmethod
    def run(
        self,
        check: ReplayCheck,
        *,
        episode: EpisodeRecord,
    ) -> ReplayCheckResult:
        raise NotImplementedError


class CallableReplayAdapter(ReplayAdapter):
    def __init__(
        self,
        runner: Callable[
            [ReplayCheck, EpisodeRecord],
            ReplayCheckResult,
        ],
    ) -> None:
        self.runner = runner

    def run(
        self,
        check: ReplayCheck,
        *,
        episode: EpisodeRecord,
    ) -> ReplayCheckResult:
        return self.runner(check, episode)


class ReplayValidator:
    def __init__(
        self,
        *,
        adapter: ReplayAdapter,
        require_evidence: bool = True,
    ) -> None:
        self.adapter = adapter
        self.require_evidence = require_evidence

    def validate(
        self,
        episode: EpisodeRecord,
        checks: tuple[ReplayCheck, ...],
    ) -> ReplayValidationResult:
        episode_fingerprint = episode.fingerprint()

        if episode.outcome != "success":
            return ReplayValidationResult(
                accepted=False,
                reason="source_episode_not_successful",
                episode_fingerprint=episode_fingerprint,
            )

        if not checks:
            return ReplayValidationResult(
                accepted=False,
                reason="missing_replay_checks",
                episode_fingerprint=episode_fingerprint,
            )

        check_ids = [check.check_id for check in checks]
        if len(check_ids) != len(set(check_ids)):
            return ReplayValidationResult(
                accepted=False,
                reason="duplicate_replay_check_id",
                episode_fingerprint=episode_fingerprint,
            )

        results: list[ReplayCheckResult] = []
        for check in checks:
            try:
                result = self.adapter.run(check, episode=episode)
            except Exception as exc:
                result = ReplayCheckResult(
                    check_id=check.check_id,
                    status="ERROR",
                    details={
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )

            if result.check_id != check.check_id:
                return ReplayValidationResult(
                    accepted=False,
                    reason="replay_result_check_id_mismatch",
                    episode_fingerprint=episode_fingerprint,
                    check_results=tuple(results),
                )

            results.append(result)

            if check.required and result.status != "PASS":
                return ReplayValidationResult(
                    accepted=False,
                    reason=f"required_replay_check_{result.status.lower()}",
                    episode_fingerprint=episode_fingerprint,
                    check_results=tuple(results),
                )

            if (
                check.required
                and self.require_evidence
                and not result.evidence_refs
            ):
                return ReplayValidationResult(
                    accepted=False,
                    reason="required_replay_check_missing_evidence",
                    episode_fingerprint=episode_fingerprint,
                    check_results=tuple(results),
                )

        required_count = sum(1 for check in checks if check.required)
        if required_count == 0:
            return ReplayValidationResult(
                accepted=False,
                reason="no_required_replay_checks",
                episode_fingerprint=episode_fingerprint,
                check_results=tuple(results),
            )

        verification_ref = _verification_ref(
            episode_fingerprint,
            checks,
            tuple(results),
        )
        return ReplayValidationResult(
            accepted=True,
            reason="replay_verified",
            episode_fingerprint=episode_fingerprint,
            verification_ref=verification_ref,
            check_results=tuple(results),
        )


def _verification_ref(
    episode_fingerprint: str,
    checks: tuple[ReplayCheck, ...],
    results: tuple[ReplayCheckResult, ...],
) -> str:
    payload = {
        "episode_fingerprint": episode_fingerprint,
        "checks": [
            {
                "check_id": check.check_id,
                "kind": check.kind,
                "payload": check.payload,
                "required": check.required,
            }
            for check in checks
        ],
        "results": [
            {
                "check_id": result.check_id,
                "status": result.status,
                "evidence_refs": list(result.evidence_refs),
                "details": result.details,
            }
            for result in results
        ],
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"replay:{sha256(encoded).hexdigest()}"
