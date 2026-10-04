from __future__ import annotations

from dataclasses import dataclass, field, replace
from hashlib import sha256
import json
import time
import uuid

from yisang.experience.models import ReplayReport

from .telemetry import EgoTelemetryEvent, EgoTelemetryPort

from .port import (
    EgoAuditEvent,
    EgoInvalidationCandidate,
    EgoPort,
)


class EgoLifecycleError(ValueError):
    pass


@dataclass(frozen=True)
class EgoLifecycleReceipt:
    receipt_id: str
    action: str
    ego_id: str
    version: str
    actor: str
    reason: str
    status: str
    candidate_id: str | None = None
    approval_ref: str | None = None
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.receipt_id.strip():
            raise ValueError("receipt_id must be non-empty")
        if self.action not in {"approve_invalidation", "reject_invalidation"}:
            raise ValueError(f"unsupported lifecycle receipt action: {self.action}")
        if self.status not in {"applied", "rejected"}:
            raise ValueError(f"unsupported lifecycle receipt status: {self.status}")


class EgoLifecycleGuard:
    """Turns later replay regressions into reviewable invalidation candidates."""

    def __init__(
        self,
        egos: EgoPort,
        telemetry: EgoTelemetryPort | None = None,
    ) -> None:
        self.egos = egos
        self.telemetry = telemetry

    def assess_replay(
        self,
        *,
        ego_id: str,
        version: str,
        replay: ReplayReport,
        reason: str = "post-install replay regression",
    ) -> EgoInvalidationCandidate | None:
        installed = self.egos.get(ego_id, version)
        if installed is None:
            raise KeyError(f"{ego_id}@{version}")
        if not installed.active:
            raise EgoLifecycleError(
                "only the active E.G.O version may create invalidation candidates"
            )

        failed = tuple(result for result in replay.results if not result.passed)
        if self.telemetry is not None:
            self.telemetry.record(
                EgoTelemetryEvent.replay_health(
                    ego_id=ego_id,
                    version=version,
                    replay_run_id=replay.run_id,
                    success=not failed,
                )
            )
        if not failed:
            return None
        failed_tests = tuple(result.test_id for result in failed)
        evidence_refs = tuple(
            dict.fromkeys(
                ref
                for result in failed
                for ref in result.evidence_refs
            )
        )
        candidate_id = _candidate_id(
            ego_id=ego_id,
            version=version,
            replay_run_id=replay.run_id,
            failed_tests=failed_tests,
        )
        existing = self.egos.get_invalidation_candidate(candidate_id)
        if existing is not None:
            return existing

        candidate = EgoInvalidationCandidate(
            candidate_id=candidate_id,
            ego_id=ego_id,
            version=version,
            source_artifact_id=installed.source_artifact_id,
            replay_run_id=replay.run_id,
            failed_tests=failed_tests,
            evidence_refs=evidence_refs,
            reason=reason,
        )
        self.egos.put_invalidation_candidate(candidate)
        self.egos.record_audit(
            EgoAuditEvent(
                event_id=f"ego-event-{uuid.uuid4().hex[:12]}",
                action="invalidation_candidate_created",
                ego_id=ego_id,
                version=version,
                actor="replay-monitor",
                reason=reason,
                candidate_id=candidate.candidate_id,
                metadata={
                    "replay_run_id": replay.run_id,
                    "failed_tests": list(failed_tests),
                    "evidence_refs": list(evidence_refs),
                },
            )
        )
        return candidate

    def approve(
        self,
        candidate_id: str,
        *,
        actor: str,
        approval_ref: str,
        reason: str,
    ) -> EgoLifecycleReceipt:
        candidate = self._pending(candidate_id)
        installed = self.egos.get(candidate.ego_id, candidate.version)
        if installed is None:
            raise KeyError(f"{candidate.ego_id}@{candidate.version}")
        if not installed.active:
            raise EgoLifecycleError(
                "invalidation target is no longer the active E.G.O version"
            )
        actor = _required(actor, "actor")
        approval_ref = _required(approval_ref, "approval_ref")
        reason = _required(reason, "reason")

        self.egos.disable(
            candidate.ego_id,
            candidate.version,
            reason=reason,
            actor=actor,
            approval_ref=approval_ref,
        )
        resolved = replace(
            candidate,
            status="approved",
            resolved_at=time.time(),
            resolution_actor=actor,
            approval_ref=approval_ref,
            resolution_reason=reason,
        )
        self.egos.update_invalidation_candidate(resolved)
        self.egos.record_audit(
            EgoAuditEvent(
                event_id=f"ego-event-{uuid.uuid4().hex[:12]}",
                action="invalidation_candidate_approved",
                ego_id=candidate.ego_id,
                version=candidate.version,
                actor=actor,
                reason=reason,
                approval_ref=approval_ref,
                candidate_id=candidate.candidate_id,
            )
        )
        return EgoLifecycleReceipt(
            receipt_id=f"ego-lifecycle-{uuid.uuid4().hex[:12]}",
            action="approve_invalidation",
            ego_id=candidate.ego_id,
            version=candidate.version,
            actor=actor,
            reason=reason,
            status="applied",
            candidate_id=candidate.candidate_id,
            approval_ref=approval_ref,
        )

    def reject(
        self,
        candidate_id: str,
        *,
        actor: str,
        reason: str,
    ) -> EgoLifecycleReceipt:
        candidate = self._pending(candidate_id)
        actor = _required(actor, "actor")
        reason = _required(reason, "reason")
        resolved = replace(
            candidate,
            status="rejected",
            resolved_at=time.time(),
            resolution_actor=actor,
            resolution_reason=reason,
        )
        self.egos.update_invalidation_candidate(resolved)
        self.egos.record_audit(
            EgoAuditEvent(
                event_id=f"ego-event-{uuid.uuid4().hex[:12]}",
                action="invalidation_candidate_rejected",
                ego_id=candidate.ego_id,
                version=candidate.version,
                actor=actor,
                reason=reason,
                candidate_id=candidate.candidate_id,
            )
        )
        return EgoLifecycleReceipt(
            receipt_id=f"ego-lifecycle-{uuid.uuid4().hex[:12]}",
            action="reject_invalidation",
            ego_id=candidate.ego_id,
            version=candidate.version,
            actor=actor,
            reason=reason,
            status="rejected",
            candidate_id=candidate.candidate_id,
        )

    def _pending(self, candidate_id: str) -> EgoInvalidationCandidate:
        candidate = self.egos.get_invalidation_candidate(candidate_id)
        if candidate is None:
            raise KeyError(candidate_id)
        if candidate.status != "pending":
            raise EgoLifecycleError(
                f"invalidation candidate is already {candidate.status}"
            )
        return candidate


def _candidate_id(
    *,
    ego_id: str,
    version: str,
    replay_run_id: str,
    failed_tests: tuple[str, ...],
) -> str:
    payload = json.dumps(
        {
            "ego_id": ego_id,
            "version": version,
            "replay_run_id": replay_run_id,
            "failed_tests": list(failed_tests),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "ego-invalid-" + sha256(payload.encode("utf-8")).hexdigest()[:16]


def _required(value: str, name: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise ValueError(f"{name} must be non-empty")
    return normalized
