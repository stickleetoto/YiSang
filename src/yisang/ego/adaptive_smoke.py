from __future__ import annotations

import argparse
import json

from yisang.ego.adaptive_router import AdaptiveCapabilityRouter
from yisang.ego.models import EgoManifest
from yisang.ego.telemetry import EgoAdaptiveScorer, EgoTelemetryEvent
from yisang.ego.telemetry_memory import InMemoryEgoTelemetryPort


def _ego(ego_id: str) -> EgoManifest:
    return EgoManifest(
        ego_id=ego_id,
        name=ego_id,
        provides=("python.debug",),
        schema_version=2,
        version="1.0.0",
        description="Diagnose Python pytest failures.",
        tags=("python", "pytest", "debugging"),
        examples=("pytest failure",),
        detail_level="metadata",
    )


def _record(
    port: InMemoryEgoTelemetryPort,
    ego_id: str,
    outcomes: tuple[bool, ...],
) -> None:
    for index, success in enumerate(outcomes):
        port.record(
            EgoTelemetryEvent.runtime_use(
                ego_id=ego_id,
                version="1.0.0",
                request_id=f"{ego_id}-runtime-{index}",
                success=success,
                verification_status="PASS" if success else "FAIL",
                latency_ms=10.0 + index,
                action_failure_count=0 if success else 1,
                created_at=1000.0 + index,
            )
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-ego-adaptive-smoke")
    parser.parse_args(argv)

    port = InMemoryEgoTelemetryPort()
    _record(port, "ego.stable", (True, True, True, True))
    _record(port, "ego.regressed", (False, False, False, False))
    port.record(
        EgoTelemetryEvent.replay_health(
            ego_id="ego.stable",
            version="1.0.0",
            replay_run_id="stable-replay",
            success=True,
            created_at=1010.0,
        )
    )
    port.record(
        EgoTelemetryEvent.replay_health(
            ego_id="ego.regressed",
            version="1.0.0",
            replay_run_id="regressed-replay",
            success=False,
            created_at=1010.0,
        )
    )

    scorer = EgoAdaptiveScorer(
        min_samples=3,
        saturation_samples=3,
        half_life_days=365,
        clock=lambda: 1020.0,
    )
    router = AdaptiveCapabilityRouter(port, scorer=scorer)
    stable = scorer.summary(
        port,
        ego_id="ego.stable",
        version="1.0.0",
        now=1020.0,
    )
    regressed = scorer.summary(
        port,
        ego_id="ego.regressed",
        version="1.0.0",
        now=1020.0,
    )
    routed = router.route(
        "python pytest debugging",
        [_ego("ego.regressed"), _ego("ego.stable")],
        limit=2,
    )

    payload = {
        "ready": bool(
            stable.routing_adjustment > 0
            and regressed.routing_adjustment < 0
            and routed[0].ego_id == "ego.stable"
        ),
        "min_samples": scorer.min_samples,
        "stable_adjustment": stable.routing_adjustment,
        "regressed_adjustment": regressed.routing_adjustment,
        "stable_weighted_success_rate": stable.weighted_success_rate,
        "regressed_weighted_success_rate": regressed.weighted_success_rate,
        "selected_order": [ego.ego_id for ego in routed],
        "replay_health_weighted": True,
        "bounded_adjustment": max(
            abs(stable.routing_adjustment),
            abs(regressed.routing_adjustment),
        ) <= scorer.max_adjustment,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
