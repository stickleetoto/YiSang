from __future__ import annotations

from abc import ABC, abstractmethod

from .models import PromotionApplyReceipt, PromotionArtifact


class PromotionPort(ABC):
    """Authoritative storage boundary for validated promotion artifacts."""

    @abstractmethod
    def put(self, artifact: PromotionArtifact) -> None:
        raise NotImplementedError

    @abstractmethod
    def get(self, artifact_id: str) -> PromotionArtifact | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(self) -> tuple[PromotionArtifact, ...]:
        raise NotImplementedError

    @abstractmethod
    def invalidate(self, artifact_id: str, *, reason: str) -> PromotionArtifact:
        raise NotImplementedError

    @abstractmethod
    def record_receipt(self, receipt: PromotionApplyReceipt) -> None:
        raise NotImplementedError

    @abstractmethod
    def receipts(
        self,
        artifact_id: str | None = None,
    ) -> tuple[PromotionApplyReceipt, ...]:
        raise NotImplementedError

    def find_applied(
        self,
        *,
        artifact_id: str,
        target_ref: str,
    ) -> PromotionApplyReceipt | None:
        for receipt in self.receipts(artifact_id):
            if receipt.target_ref == target_ref and receipt.status in {
                "applied",
                "already_applied",
            }:
                return receipt
        return None
