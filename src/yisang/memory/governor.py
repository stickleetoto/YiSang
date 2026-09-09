from .models import MemoryProposal, GovernanceDecision
from .port import MemoryPort

class MemoryGovernor:
    def __init__(self, *, min_confidence: float = 0.60, require_evidence: bool = True) -> None:
        self.min_confidence = min_confidence
        self.require_evidence = require_evidence

    def evaluate(self, proposal: MemoryProposal, memory: MemoryPort) -> GovernanceDecision:
        if proposal.confidence < self.min_confidence:
            return GovernanceDecision(False, "confidence_below_threshold")

        if self.require_evidence and not proposal.evidence:
            return GovernanceDecision(False, "missing_evidence")

        normalized = proposal.content.strip().lower()
        for record in memory.all():
            if record.content.strip().lower() == normalized:
                return GovernanceDecision(False, "duplicate")

        return GovernanceDecision(True, "accepted")
