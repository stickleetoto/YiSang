from yisang.ego.adaptive_router import AdaptiveCapabilityRouter
from yisang.ego.models import EgoManifest
from yisang.ego.telemetry import EgoAdaptiveScorer, EgoTelemetryEvent
from yisang.ego.telemetry_memory import InMemoryEgoTelemetryPort


def _ego(ego_id):
    return EgoManifest(
        ego_id=ego_id,
        name=ego_id,
        provides=("python.debug",),
        schema_version=2,
        version="1.0.0",
        description="python debugging",
        tags=("python", "debugging"),
        detail_level="metadata",
    )


def _record(port, ego_id, successes):
    for index, success in enumerate(successes):
        port.record(
            EgoTelemetryEvent.runtime_use(
                ego_id=ego_id,
                version="1.0.0",
                request_id=f"{ego_id}-{index}",
                success=success,
                verification_status="PASS" if success else "FAIL",
                latency_ms=5.0,
                action_failure_count=0 if success else 1,
                created_at=1000.0 + index,
            )
        )


def test_adaptive_router_uses_bounded_feedback_to_break_metadata_tie():
    port = InMemoryEgoTelemetryPort()
    _record(port, "ego.good", [True, True, True, True])
    _record(port, "ego.bad", [False, False, False, False])
    router = AdaptiveCapabilityRouter(
        port,
        scorer=EgoAdaptiveScorer(
            min_samples=3,
            saturation_samples=3,
            half_life_days=365,
            clock=lambda: 1020.0,
        ),
    )

    found = router.route(
        "python debugging",
        [_ego("ego.bad"), _ego("ego.good")],
        limit=2,
    )

    assert [ego.ego_id for ego in found] == ["ego.good", "ego.bad"]


def test_adaptive_router_does_not_use_two_sample_noise():
    port = InMemoryEgoTelemetryPort()
    _record(port, "ego.a", [False, False])
    _record(port, "ego.b", [True, True])
    router = AdaptiveCapabilityRouter(
        port,
        scorer=EgoAdaptiveScorer(min_samples=3),
    )

    found = router.route(
        "python debugging",
        [_ego("ego.a"), _ego("ego.b")],
        limit=2,
    )

    assert [ego.ego_id for ego in found] == ["ego.a", "ego.b"]
