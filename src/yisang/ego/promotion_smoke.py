from __future__ import annotations

import argparse
import json

from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.memory_port import InMemoryEgoPort
from yisang.ego.registry_view import DurableEgoRegistryView
from yisang.ego.router_v2 import HybridCapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier
from yisang.experience.application import DurableEgoApplyAdapter
from yisang.experience.ledger import InMemoryPromotionLedger
from yisang.experience.models import (
    ExperienceEvidence,
    LessonCandidate,
    PromotionApplyRequest,
    ReplayCaseResult,
    ReplayReport,
)
from yisang.experience.promotion import PromotionGate


def _promote(version: str, content: str):
    candidate = LessonCandidate(
        candidate_id=f"candidate-{version}",
        kind="procedure",
        target="ego_procedure",
        title="Learned Python Debugger",
        proposed_content=content,
        source_episode_ids=(f"episode-{version}-1", f"episode-{version}-2"),
        source_evidence=(
            ExperienceEvidence(
                evidence_ref=f"test:{version}:1",
                source_type="test_result",
                summary="ordered replay passed",
                verified=True,
            ),
        ),
        trigger_conditions=("python pytest failure",),
        validation_tests=(f"replay-{version}",),
        success_count=3,
        scope="python.debug",
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


def _request(artifact_id: str):
    return PromotionApplyRequest(
        artifact_id=artifact_id,
        target_ref="ego:ego.learned.python-debug",
        actor="human-reviewer",
        approval_ref=f"approval:{artifact_id}",
        reason="ordered replay validated",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-ego-promotion-smoke")
    parser.parse_args(argv)

    first = _promote("1", "Inspect pytest failure before editing.")
    second = _promote("2", "Inspect traceback, patch minimally, rerun pytest.")
    promotions = InMemoryPromotionLedger()
    promotions.put(first)
    promotions.put(second)
    egos = InMemoryEgoPort()
    adapter = DurableEgoApplyAdapter(promotions, egos)

    first_receipt = adapter.apply(
        _request(first.artifact_id),
        ego_id="ego.learned.python-debug",
    )
    second_receipt = adapter.apply(
        _request(second.artifact_id),
        ego_id="ego.learned.python-debug",
    )

    view = DurableEgoRegistryView(egos)
    routed_before = HybridCapabilityRouter().route(
        "python pytest failure traceback",
        view.list_all(),
        limit=1,
    )
    active_before = view.get("ego.learned.python-debug")

    engines = EngineRouter()
    engines.register(EchoEngine("ego-smoke", "EGO"))
    runtime = YiSangRuntime(
        identity=IdentityCharter("ego-promotion-smoke", "YiSang"),
        state=AgentState(active_engine="ego-smoke"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=view,
        capability_router=HybridCapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )
    runtime_response = runtime.run(
        YiSangRequest("ego-promotion-runtime", "python pytest failure traceback")
    )

    restored = egos.rollback(
        "ego.learned.python-debug",
        "0.0.1",
        reason="smoke rollback proof",
    )
    active_after = view.get("ego.learned.python-debug")

    payload = {
        "ready": bool(
            first_receipt.status == "applied"
            and second_receipt.status == "applied"
            and active_before.version == "0.0.2"
            and routed_before
            and routed_before[0].version == "0.0.2"
            and runtime_response.used_ego_ids == ["ego.learned.python-debug"]
            and "1 E.G.O modules" in runtime_response.text
            and restored.version == "0.0.1"
            and active_after.version == "0.0.1"
        ),
        "installed_versions": [
            item.version
            for item in egos.list_versions("ego.learned.python-debug")
        ],
        "active_after_second_apply": active_before.version,
        "routed_version": (
            routed_before[0].version if routed_before else None
        ),
        "runtime_selected_ego_ids": runtime_response.used_ego_ids,
        "runtime_context_used_promoted_ego": "1 E.G.O modules" in runtime_response.text,
        "rollback_target": restored.version,
        "active_after_rollback": active_after.version,
        "promotion_receipts": (
            len(promotions.receipts(first.artifact_id))
            + len(promotions.receipts(second.artifact_id))
        ),
        "package_digest_bound": bool(
            active_after.package_digest
        ),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
