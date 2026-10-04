from __future__ import annotations

from yisang.ego.generated import build_promoted_ego_manifest
from yisang.ego.lifecycle import EgoLifecycleGuard
from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.port import InstalledEgoPackage
from yisang.ego.sqlite_port import SQLiteEgoPort
from yisang.experience.models import (
    PromotionArtifact,
    ReplayCaseResult,
    ReplayReport,
)


def _artifact(artifact_id="p1", version="1"):
    return PromotionArtifact(
        artifact_id=artifact_id,
        candidate_id=f"candidate-{artifact_id}",
        kind="procedure",
        target="ego_procedure",
        title="Learned debugger",
        content="debug safely",
        version=version,
        source_episode_ids=("episode-1",),
        evidence_refs=("test:source",),
        validation_run_id="replay-source",
        trigger_conditions=("pytest failure",),
        scope="python.debug",
    )


def _install(port, artifact=None):
    artifact = artifact or _artifact()
    manifest = build_promoted_ego_manifest(
        artifact,
        ego_id="ego.learned.debug",
    )
    return port.install(
        InstalledEgoPackage(
            ego_id=manifest.ego_id,
            version=manifest.version,
            manifest=manifest,
            source_artifact_id=artifact.artifact_id,
            approval_ref="approval:install",
            status_reason="validated install",
        ),
        actor="reviewer",
        approval_ref="approval:install",
    )


def _failed_replay(run_id="replay-health-1"):
    return ReplayReport(
        candidate_id="health-check",
        run_id=run_id,
        results=(
            ReplayCaseResult(
                test_id="health:1",
                passed=False,
                evidence_refs=("replay-evidence:failure",),
                detail="regression",
            ),
        ),
    )


def test_failed_replay_creates_pending_candidate_without_auto_disable():
    port = InMemoryEgoPort()
    installed = _install(port)
    guard = EgoLifecycleGuard(port)

    candidate = guard.assess_replay(
        ego_id=installed.ego_id,
        version=installed.version,
        replay=_failed_replay(),
    )

    assert candidate is not None
    assert candidate.status == "pending"
    assert candidate.failed_tests == ("health:1",)
    assert port.get(installed.ego_id, installed.version).active is True
    assert port.list_invalidation_candidates(status="pending") == (candidate,)
    assert "invalidation_candidate_created" in [
        event.action for event in port.audit_events(installed.ego_id)
    ]


def test_rejected_candidate_keeps_ego_active():
    port = InMemoryEgoPort()
    installed = _install(port)
    guard = EgoLifecycleGuard(port)
    candidate = guard.assess_replay(
        ego_id=installed.ego_id,
        version=installed.version,
        replay=_failed_replay(),
    )
    receipt = guard.reject(
        candidate.candidate_id,
        actor="reviewer",
        reason="fixture was invalid",
    )

    assert receipt.status == "rejected"
    assert port.get(installed.ego_id, installed.version).active is True
    assert port.get_invalidation_candidate(candidate.candidate_id).status == "rejected"


def test_approved_candidate_disables_active_ego():
    port = InMemoryEgoPort()
    installed = _install(port)
    guard = EgoLifecycleGuard(port)
    candidate = guard.assess_replay(
        ego_id=installed.ego_id,
        version=installed.version,
        replay=_failed_replay(),
    )
    receipt = guard.approve(
        candidate.candidate_id,
        actor="reviewer",
        approval_ref="approval:disable:1",
        reason="confirmed replay regression",
    )

    assert receipt.status == "applied"
    assert port.get(installed.ego_id, installed.version).state == "disabled"
    assert port.get_invalidation_candidate(candidate.candidate_id).status == "approved"
    actions = [event.action for event in port.audit_events(installed.ego_id)]
    assert "disable" in actions
    assert "invalidation_candidate_approved" in actions


def test_successful_replay_does_not_create_candidate():
    port = InMemoryEgoPort()
    installed = _install(port)
    guard = EgoLifecycleGuard(port)
    replay = ReplayReport(
        candidate_id="health-check",
        results=(ReplayCaseResult(test_id="health:1", passed=True),),
    )

    assert guard.assess_replay(
        ego_id=installed.ego_id,
        version=installed.version,
        replay=replay,
    ) is None
    assert port.list_invalidation_candidates() == ()


def test_sqlite_audit_and_invalidation_survive_restart(tmp_path):
    db = tmp_path / "ego-health.db"
    with SQLiteEgoPort(db) as port:
        installed = _install(port)
        guard = EgoLifecycleGuard(port)
        candidate = guard.assess_replay(
            ego_id=installed.ego_id,
            version=installed.version,
            replay=_failed_replay(),
        )

    with SQLiteEgoPort(db) as port:
        loaded = port.get_invalidation_candidate(candidate.candidate_id)
        assert loaded is not None
        assert loaded.status == "pending"
        assert any(
            event.action == "invalidation_candidate_created"
            for event in port.audit_events("ego.learned.debug")
        )
        EgoLifecycleGuard(port).approve(
            candidate.candidate_id,
            actor="reviewer",
            approval_ref="approval:disable:sqlite",
            reason="confirmed after restart",
        )

    with SQLiteEgoPort(db) as port:
        assert port.get("ego.learned.debug", "0.0.1").state == "disabled"
        assert port.get_invalidation_candidate(candidate.candidate_id).status == "approved"
