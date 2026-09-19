from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from .governor import MemoryGovernor
from .models import MemoryProposal, MemoryRecord
from .port import MemoryPort
from .quarantine import QuarantinedMemory, QuarantinePort


class MemoryWriteStatus(str, Enum):
    COMMITTED = "committed"
    QUARANTINED = "quarantined"
    REJECTED = "rejected"


@dataclass(frozen=True)
class MemoryWriteResult:
    status: MemoryWriteStatus
    reason: str
    record: MemoryRecord | None = None
    quarantine: QuarantinedMemory | None = None
    risk_flags: tuple[str, ...] = ()


class MemoryWritePipeline:
    """Single governed entry point for durable-memory writes."""

    def __init__(
        self,
        *,
        memory: MemoryPort,
        governor: MemoryGovernor,
        quarantine: QuarantinePort,
    ) -> None:
        self.memory = memory
        self.governor = governor
        self.quarantine = quarantine

    def submit(self, proposal: MemoryProposal) -> MemoryWriteResult:
        decision = self.governor.evaluate(proposal, self.memory)

        if decision.accepted:
            record = self.memory.commit(proposal)
            if proposal.supersedes_id is not None:
                self.memory.supersede(
                    proposal.supersedes_id,
                    superseded_by_id=record.memory_id,
                    actor=proposal.writer or proposal.source_engine,
                    reason="superseded_by_new_memory",
                    evidence_refs=tuple(proposal.evidence),
                )
            return MemoryWriteResult(
                status=MemoryWriteStatus.COMMITTED,
                reason=decision.reason,
                record=record,
                risk_flags=decision.risk_flags,
            )

        if decision.quarantine:
            item = self.quarantine.put(
                proposal,
                reason=decision.reason,
                risk_flags=decision.risk_flags,
            )
            return MemoryWriteResult(
                status=MemoryWriteStatus.QUARANTINED,
                reason=decision.reason,
                quarantine=item,
                risk_flags=decision.risk_flags,
            )

        return MemoryWriteResult(
            status=MemoryWriteStatus.REJECTED,
            reason=decision.reason,
            risk_flags=decision.risk_flags,
        )

    def release(
        self,
        quarantine_id: str,
        *,
        reviewer: str,
        trust_class: str = "trusted",
        additional_evidence: tuple[str, ...] = (),
    ) -> MemoryWriteResult:
        if not reviewer.strip():
            raise ValueError("reviewer must be non-empty")

        item = self.quarantine.get(quarantine_id)
        if item is None:
            raise KeyError(f"quarantined memory not found: {quarantine_id}")

        proposal = replace(
            item.proposal,
            trust_class=trust_class,
            writer=reviewer,
            evidence=[
                *item.proposal.evidence,
                *additional_evidence,
                f"quarantine-review:{reviewer}",
            ],
            metadata={
                **item.proposal.metadata,
                "released_from_quarantine": quarantine_id,
                "reviewer": reviewer,
            },
        )

        decision = self.governor.evaluate(proposal, self.memory)
        if not decision.accepted:
            return MemoryWriteResult(
                status=(
                    MemoryWriteStatus.QUARANTINED
                    if decision.quarantine
                    else MemoryWriteStatus.REJECTED
                ),
                reason=decision.reason,
                quarantine=item,
                risk_flags=decision.risk_flags,
            )

        record = self.memory.commit(proposal)
        self.quarantine.remove(quarantine_id)
        return MemoryWriteResult(
            status=MemoryWriteStatus.COMMITTED,
            reason="released_from_quarantine",
            record=record,
            risk_flags=decision.risk_flags,
        )

    def revoke(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        """Revoke a durable memory without deleting its audit trail."""
        return self.memory.invalidate(
            memory_id,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )

    def revalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        """Restore a previously revoked memory after external review."""
        return self.memory.revalidate(
            memory_id,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )

    def discard(self, quarantine_id: str) -> QuarantinedMemory | None:
        return self.quarantine.remove(quarantine_id)
