from __future__ import annotations

from .models import PromotionApplyReceipt, PromotionArtifact
from .port import PromotionPort


class InMemoryPromotionLedger(PromotionPort):
    """Reference PromotionPort for tests and ephemeral runtimes."""

    def __init__(self) -> None:
        self._artifacts: dict[str, PromotionArtifact] = {}
        self._receipts: dict[str, PromotionApplyReceipt] = {}

    def add(self, artifact: PromotionArtifact) -> None:
        self.put(artifact)

    def put(self, artifact: PromotionArtifact) -> None:
        if artifact.artifact_id in self._artifacts:
            raise ValueError(f"duplicate promotion artifact: {artifact.artifact_id}")
        self._artifacts[artifact.artifact_id] = artifact

    def get(self, artifact_id: str) -> PromotionArtifact | None:
        return self._artifacts.get(artifact_id)

    def list_all(self) -> tuple[PromotionArtifact, ...]:
        return tuple(
            self._artifacts[artifact_id]
            for artifact_id in sorted(self._artifacts)
        )

    def list_active(self) -> tuple[PromotionArtifact, ...]:
        return tuple(artifact for artifact in self.list_all() if artifact.active)

    def invalidate(self, artifact_id: str, *, reason: str) -> PromotionArtifact:
        artifact = self._artifacts.get(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        artifact.invalidate(reason)
        return artifact

    def record_receipt(self, receipt: PromotionApplyReceipt) -> None:
        if receipt.apply_id in self._receipts:
            raise ValueError(f"duplicate apply receipt: {receipt.apply_id}")
        self._receipts[receipt.apply_id] = receipt

    def receipts(
        self,
        artifact_id: str | None = None,
    ) -> tuple[PromotionApplyReceipt, ...]:
        receipts = tuple(
            self._receipts[apply_id]
            for apply_id in sorted(self._receipts)
        )
        if artifact_id is None:
            return receipts
        return tuple(
            receipt
            for receipt in receipts
            if receipt.artifact_id == artifact_id
        )
