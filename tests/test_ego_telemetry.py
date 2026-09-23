from __future__ import annotations

from yisang.ego.telemetry import EgoAdaptiveScorer, EgoTelemetryEvent
from yisang.ego.telemetry_memory import InMemoryEgoTelemetryPort
from yisang.ego.telemetry_sqlite import SQLiteEgoTelemetryPort


def _event(index, success, *, kind="runtime_use", created_at=1000.0):
    if kind == "replay_health":
        return EgoTelemetryEvent.replay_health(
            ego_id="ego.debug",
            version="1.0.0",
            replay_run_id=f"replay-{index}",
            success=success,
            created_at=created_at + index,
        )
    return EgoTelemetryEvent.runtime_use(
        ego_id="ego.debug",
        version="1.0.0",
        request_id=f"request-{index}",
        success=success,
        verification_status="PASS" if success else "FAIL",
        latency_ms=10.0 + index,
        action_failure_count=0 if success else 1,
        created_at=created_at + index,
    )


def test_scorer_requires_minimum_samples():
    port = InMemoryEgoTelemetryPort()
    port.record(_event(1, True))
    port.record(_event(2, True))

    summary = EgoAdaptiveScorer(min_samples=3).summary(
        port,
        ego_id="ego.debug",
        version="1.0.0",
        now=1010.0,
    )

    assert summary.sample_count == 2
    assert summary.routing_adjustment == 0.0


def test_scorer_is_bounded_and_replay_health_has_weight():
    good = InMemoryEgoTelemetryPort()
    bad = InMemoryEgoTelemetryPort()
    for index in range(6):
        good.record(_event(index, True))
        bad.record(_event(index, False))
    good.record(_event(10, True, kind="replay_health"))
    bad.record(_event(10, False, kind="replay_health"))

    scorer = EgoAdaptiveScorer(
        min_samples=3,
        saturation_samples=3,
        max_adjustment=0.35,
    )
    good_summary = scorer.summary(
        good,
        ego_id="ego.debug",
        version="1.0.0",
        now=1020.0,
    )
    bad_summary = scorer.summary(
        bad,
        ego_id="ego.debug",
        version="1.0.0",
        now=1020.0,
    )

    assert 0 < good_summary.routing_adjustment <= 0.35
    assert -0.35 <= bad_summary.routing_adjustment < 0
    assert good_summary.replay_passes == 1
    assert bad_summary.replay_failures == 1


def test_sqlite_telemetry_survives_restart(tmp_path):
    db = tmp_path / "telemetry.db"
    event = _event(1, True)
    with SQLiteEgoTelemetryPort(db) as port:
        port.record(event)
    with SQLiteEgoTelemetryPort(db) as port:
        assert port.events(
            ego_id="ego.debug",
            version="1.0.0",
        ) == (event,)
