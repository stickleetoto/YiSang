from yisang.ego.generated import build_promoted_ego_manifest
from yisang.ego.lifecycle import EgoLifecycleGuard
from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.port import InstalledEgoPackage
from yisang.ego.telemetry_memory import InMemoryEgoTelemetryPort
from yisang.experience.models import (
    PromotionArtifact,
    ReplayCaseResult,
    ReplayReport,
)


def test_lifecycle_guard_records_replay_health_telemetry():
    artifact = PromotionArtifact(
        artifact_id="p-health",
        candidate_id="candidate-health",
        kind="procedure",
        target="ego_procedure",
        title="Health",
        content="safe procedure",
        version="1",
        source_episode_ids=("e1",),
        evidence_refs=("test:1",),
        validation_run_id="source",
        trigger_conditions=("health",),
        scope="health",
    )
    manifest = build_promoted_ego_manifest(
        artifact,
        ego_id="ego.health",
    )
    port = InMemoryEgoPort()
    port.install(
        InstalledEgoPackage(
            ego_id=manifest.ego_id,
            version=manifest.version,
            manifest=manifest,
        )
    )
    telemetry = InMemoryEgoTelemetryPort()
    guard = EgoLifecycleGuard(port, telemetry=telemetry)
    replay = ReplayReport(
        candidate_id="health",
        run_id="health-run",
        results=(
            ReplayCaseResult(
                test_id="health:test",
                passed=False,
                evidence_refs=("proof:fail",),
            ),
        ),
    )

    candidate = guard.assess_replay(
        ego_id="ego.health",
        version="0.0.1",
        replay=replay,
    )

    assert candidate is not None
    events = telemetry.events(ego_id="ego.health", version="0.0.1")
    assert len(events) == 1
    assert events[0].kind == "replay_health"
    assert events[0].success is False
