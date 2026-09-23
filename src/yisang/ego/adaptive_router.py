from __future__ import annotations

from .models import EgoManifest
from .router_v2 import HybridCapabilityRouter
from .telemetry import EgoAdaptiveScorer, EgoTelemetryPort


class AdaptiveCapabilityRouter:
    """Hybrid metadata routing with a small telemetry-derived adjustment."""

    def __init__(
        self,
        telemetry: EgoTelemetryPort,
        *,
        base: HybridCapabilityRouter | None = None,
        scorer: EgoAdaptiveScorer | None = None,
    ) -> None:
        self.telemetry = telemetry
        self.base = base or HybridCapabilityRouter()
        self.scorer = scorer or EgoAdaptiveScorer()

    def rank(
        self,
        query: str,
        egos: list[EgoManifest],
        *,
        required_capabilities: tuple[str, ...] = (),
    ):
        adjustments = {
            f"{ego.ego_id}@{ego.version}": self.scorer.summary(
                self.telemetry,
                ego_id=ego.ego_id,
                version=ego.version,
            ).routing_adjustment
            for ego in egos
        }
        return self.base.rank(
            query,
            egos,
            required_capabilities=required_capabilities,
            score_adjustments=adjustments,
        )

    def route(
        self,
        query: str,
        egos: list[EgoManifest],
        *,
        limit: int = 3,
        required_capabilities: tuple[str, ...] = (),
    ) -> list[EgoManifest]:
        if limit <= 0:
            return []
        return [
            item.ego
            for item in self.rank(
                query,
                egos,
                required_capabilities=required_capabilities,
            )[:limit]
        ]
