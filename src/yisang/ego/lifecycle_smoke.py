from __future__ import annotations

import argparse
import json

from yisang.ego.generated import build_promoted_ego_manifest
from yisang.ego.lifecycle import EgoLifecycleGuard
from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.port import InstalledEgoPackage
from yisang.ego.registry_view import DurableEgoRegistryView
from yisang.experience.models import PromotionArtifact, ReplayCaseResult, ReplayReport


def _package(artifact_id: str, version: str, content: str):
    artifact = PromotionArtifact(
        artifact_id=artifact_id,
        candidate_id=f"candidate-{artifact_id}",
        kind="procedure",
        target="ego_procedure",
        title="Learned debugger",
        content=content,
        version=version,
        source_episode_ids=("episode-1",),
        evidence_refs=("test:source",),
        validation_run_id="source-replay",
        trigger_conditions=("pytest failure",),
        scope="python.debug",
    )
    manifest = build_promoted_ego_manifest(
        artifact,
        ego_id="ego.learned.debug",
    )
    return InstalledEgoPackage(
        ego_id=manifest.ego_id,
        version=manifest.version,
        manifest=manifest,
        source_artifact_id=artifact.artifact_id,
        approval_ref=f"approval:{artifact_id}",
        status_reason="validated install",
    )


def _failed(run_id: str):
    return ReplayReport(
        candidate_id="post-install-health",
        run_id=run_id,
        results=(
            ReplayCaseResult(
                test_id="health:pytest",
                passed=False,
                evidence_refs=(f"evidence:{run_id}",),
                detail="pytest regression",
            ),
        ),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-ego-lifecycle-smoke")
    parser.parse_args(argv)

    port = InMemoryEgoPort()
    port.install(
        _package("promotion-1", "1", "stable procedure"),
        actor="reviewer",
        approval_ref="approval:promotion-1",
    )
    port.install(
        _package("promotion-2", "2", "new procedure"),
        actor="reviewer",
        approval_ref="approval:promotion-2",
    )
    guard = EgoLifecycleGuard(port)
    view = DurableEgoRegistryView(port)

    first = guard.assess_replay(
        ego_id="ego.learned.debug",
        version="0.0.2",
        replay=_failed("health-run-1"),
    )
    active_during_review = view.get("ego.learned.debug").version
    rejected = guard.reject(
        first.candidate_id,
        actor="reviewer",
        reason="bad health fixture",
    )
    active_after_reject = view.get("ego.learned.debug").version

    second = guard.assess_replay(
        ego_id="ego.learned.debug",
        version="0.0.2",
        replay=_failed("health-run-2"),
    )
    approved = guard.approve(
        second.candidate_id,
        actor="reviewer",
        approval_ref="approval:disable:2",
        reason="confirmed regression",
    )
    active_after_disable = port.list_active()
    restored = port.rollback(
        "ego.learned.debug",
        "0.0.1",
        reason="restore stable version",
        actor="reviewer",
        approval_ref="approval:rollback:1",
    )

    actions = [event.action for event in port.audit_events("ego.learned.debug")]
    payload = {
        "ready": bool(
            active_during_review == "0.0.2"
            and rejected.status == "rejected"
            and active_after_reject == "0.0.2"
            and approved.status == "applied"
            and not active_after_disable
            and restored.version == "0.0.1"
        ),
        "pending_candidate_does_not_disable": active_during_review == "0.0.2",
        "rejected_candidate_keeps_active": active_after_reject == "0.0.2",
        "approved_candidate_disables": not active_after_disable,
        "rollback_version": restored.version,
        "audit_event_count": len(actions),
        "audit_actions": actions,
        "candidate_statuses": [
            item.status for item in port.list_invalidation_candidates()
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
