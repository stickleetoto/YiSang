from __future__ import annotations

from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.registry_view import DurableEgoRegistryView
from yisang.ego.router_v2 import HybridCapabilityRouter
from yisang.experience import (
    DurableEgoApplyAdapter,
    ExperienceEvidence,
    InMemoryPromotionLedger,
    LessonCandidate,
    PromotionApplyRequest,
    PromotionGate,
    ReplayCaseResult,
    ReplayReport,
)


def _artifact(version, content):
    candidate = LessonCandidate(
        candidate_id=f"candidate-{version}",
        kind="procedure",
        target="ego_procedure",
        title="Learned Python Debugger",
        proposed_content=content,
        source_episode_ids=("episode-1",),
        source_evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:{version}",
                source_type="test_result",
                summary="replay passed",
                verified=True,
            ),
        ),
        trigger_conditions=("pytest failure", "python traceback"),
        validation_tests=(f"replay-{version}",),
        success_count=3,
        scope="python.debug",
        risk_class="normal",
        version=version,
    )
    replay = ReplayReport(
        candidate_id=candidate.candidate_id,
        results=(
            ReplayCaseResult(
                test_id=f"replay-{version}",
                passed=True,
                evidence_refs=(f"replay-proof:{version}",),
            ),
        ),
    )
    outcome = PromotionGate(min_success_count=3).promote(candidate, replay)
    assert outcome.artifact is not None
    return outcome.artifact


def _request(artifact_id):
    return PromotionApplyRequest(
        artifact_id=artifact_id,
        target_ref="ego:ego.learned.python-debug",
        actor="human-reviewer",
        approval_ref="approval:ego:1",
        reason="validated replay promotion",
    )


def test_durable_apply_installs_promoted_ego_and_is_idempotent():
    artifact = _artifact("1", "Run pytest, inspect failure, apply minimal fix.")
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    egos = InMemoryEgoPort()
    adapter = DurableEgoApplyAdapter(promotions, egos)

    first = adapter.apply(
        _request(artifact.artifact_id),
        ego_id="ego.learned.python-debug",
    )
    second = adapter.apply(
        _request(artifact.artifact_id),
        ego_id="ego.learned.python-debug",
    )

    installed = egos.get("ego.learned.python-debug")
    assert first.status == "applied"
    assert second.status == "already_applied"
    assert installed is not None
    assert installed.version == "0.0.1"
    assert installed.source_artifact_id == artifact.artifact_id
    assert installed.manifest.schema_version == 2
    assert installed.manifest.runtime_type == "prompt"
    assert installed.manifest.package_digest is not None
    assert len(promotions.receipts(artifact.artifact_id)) == 1


def test_new_promotion_version_supersedes_old_and_routes_active_only():
    first = _artifact("1", "Old debugging procedure.")
    second = _artifact("2", "New verified pytest failure procedure.")
    promotions = InMemoryPromotionLedger()
    promotions.put(first)
    promotions.put(second)
    egos = InMemoryEgoPort()
    adapter = DurableEgoApplyAdapter(promotions, egos)

    adapter.apply(
        _request(first.artifact_id),
        ego_id="ego.learned.python-debug",
    )
    adapter.apply(
        _request(second.artifact_id),
        ego_id="ego.learned.python-debug",
    )

    assert egos.get("ego.learned.python-debug", "0.0.1").state == "superseded"
    assert egos.get("ego.learned.python-debug").version == "0.0.2"

    view = DurableEgoRegistryView(egos)
    selected = HybridCapabilityRouter().route(
        "python pytest failure",
        view.list_all(),
        limit=1,
    )
    assert len(view.list_all()) == 1
    assert selected[0].version == "0.0.2"
    assert "New verified" in selected[0].instructions


def test_rollback_changes_what_registry_view_exposes():
    first = _artifact("1", "Stable procedure.")
    second = _artifact("2", "Regressed procedure.")
    promotions = InMemoryPromotionLedger()
    promotions.put(first)
    promotions.put(second)
    egos = InMemoryEgoPort()
    adapter = DurableEgoApplyAdapter(promotions, egos)
    adapter.apply(_request(first.artifact_id), ego_id="ego.learned.python-debug")
    adapter.apply(_request(second.artifact_id), ego_id="ego.learned.python-debug")

    egos.rollback(
        "ego.learned.python-debug",
        "0.0.1",
        reason="replay regression",
    )

    view = DurableEgoRegistryView(egos)
    assert view.get("ego.learned.python-debug").version == "0.0.1"
    assert view.list_all()[0].instructions == "Stable procedure."
