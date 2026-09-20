from __future__ import annotations

from .models import PromotionArtifact


class InMemoryPromotionLedger:
    """Reference ledger for accepted promotion artifacts.

    The ledger provides inspectable version history and invalidation without
    applying the artifact to E.G.O or Library stores.
    """

    def __init__(self) -> None:
        self._artifacts: dict[str, PromotionArtifact] = {}

    def add(self, artifact: PromotionArtifact) -> None:
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
