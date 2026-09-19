from __future__ import annotations

from .models import DURABLE_MEMORY_KINDS, GovernanceDecision, MemoryProposal
from .port import MemoryPort


class MemoryGovernor:
    def __init__(
        self,
        *,
        min_confidence: float = 0.60,
        require_evidence: bool = True,
        quarantine_untrusted: bool = True,
    ) -> None:
        if not 0.0 <= min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        self.min_confidence = min_confidence
        self.require_evidence = require_evidence
        self.quarantine_untrusted = quarantine_untrusted

    def evaluate(
        self,
        proposal: MemoryProposal,
        memory: MemoryPort,
    ) -> GovernanceDecision:
        if proposal.kind == "working":
            return GovernanceDecision(
                False,
                "working_memory_not_durable",
                risk_flags=("session_only",),
            )

        if proposal.kind not in DURABLE_MEMORY_KINDS:
            return GovernanceDecision(
                False,
                "unsupported_memory_kind",
                risk_flags=("schema",),
            )

        if proposal.confidence < self.min_confidence:
            return GovernanceDecision(
                False,
                "confidence_below_threshold",
                risk_flags=("low_confidence",),
            )

        if self.require_evidence and not proposal.evidence:
            return GovernanceDecision(
                False,
                "missing_evidence",
                risk_flags=("missing_provenance",),
            )

        if proposal.trust_class == "quarantined":
            return GovernanceDecision(
                False,
                "source_quarantined",
                quarantine=True,
                risk_flags=("untrusted_source",),
            )

        if self.quarantine_untrusted and proposal.trust_class == "untrusted":
            return GovernanceDecision(
                False,
                "untrusted_requires_quarantine",
                quarantine=True,
                risk_flags=("untrusted_source",),
            )

        normalized = proposal.content.strip().lower()
        for record in memory.all():
            if getattr(record, "invalidated", False):
                continue
            if record.content.strip().lower() == normalized:
                return GovernanceDecision(False, "duplicate")

        return GovernanceDecision(True, "accepted")
