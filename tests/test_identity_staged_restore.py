import json

import pytest

from yisang.context.compiler import ContextCompiler
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity import (
    AgentState,
    IdentityCharter,
    RestoreArtifacts,
    apply_restore,
    build_identity_snapshot,
    continuity_fingerprint,
    load_restore_report,
    write_restore_report,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.transfer import build_memory_archive
from yisang.verification.base import PassThroughVerifier


def _runtime():
    memory = InMemoryMemoryPort()
    memory.commit(
        MemoryProposal(
            content="stable continuity memory",
            source_engine="seed",
            confidence=0.95,
            evidence=["restore:seed"],
            trust_class="verified",
            writer="governor",
        )
    )
    egos = EgoRegistry()
    egos.register(
        EgoManifest(
            ego_id="ego.debug",
            name="Debug",
            provides=("debug",),
            keywords=("bug",),
        )
    )
    engines = EngineRouter()
    engines.register(EchoEngine("engine-a", "A"))
    engines.register(EchoEngine("engine-b", "B"))

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=AgentState(
            active_engine="engine-a",
            active_project="YiSang",
            current_goal="continue v0.5",
            tags={"phase": "v0.5"},
        ),
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )


def _snapshot_and_artifacts(runtime):
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    artifacts = RestoreArtifacts(
        memory_archive=build_memory_archive(runtime.memory),
        ego_manifests=tuple(runtime.ego_registry.list_all()),
    )
    return snapshot, artifacts


def test_apply_restore_switches_engine_and_restores_engine_independent_state():
    runtime = _runtime()
    snapshot, _ = _snapshot_and_artifacts(runtime)

    runtime.state.current_goal = "drifted"
    runtime.state.tags["phase"] = "broken"

    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
    )

    assert runtime.state.active_engine == "engine-b"
    assert runtime.state.current_goal == "continue v0.5"
    assert runtime.state.tags == {"phase": "v0.5"}
    assert report.state_restored is True
    assert report.memory_restored is False
    assert report.ego_registry_restored is False
    assert report.continuity_preserved is True


def test_apply_restore_stages_memory_before_swapping_runtime():
    runtime = _runtime()
    snapshot, artifacts = _snapshot_and_artifacts(runtime)
    expected_fingerprint = continuity_fingerprint(snapshot)

    runtime.memory.commit(
        MemoryProposal(
            content="drifted memory",
            source_engine="drift",
            confidence=0.95,
            evidence=["restore:drift"],
            trust_class="verified",
            writer="governor",
        )
    )

    old_memory = runtime.memory
    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
        artifacts=artifacts,
        memory_factory=InMemoryMemoryPort,
    )

    assert runtime.memory is not old_memory
    assert [item.content for item in runtime.memory.all()] == [
        "stable continuity memory"
    ]
    assert runtime.memory_pipeline.memory is runtime.memory
    assert report.memory_restored is True
    assert report.post_continuity_fingerprint == expected_fingerprint
    assert report.continuity_preserved is True


def test_apply_restore_stages_ego_registry_before_swap():
    runtime = _runtime()
    snapshot, artifacts = _snapshot_and_artifacts(runtime)

    runtime.ego_registry = EgoRegistry()
    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
        artifacts=artifacts,
    )

    assert [ego.ego_id for ego in runtime.ego_registry.list_all()] == ["ego.debug"]
    assert report.ego_registry_restored is True
    assert report.continuity_preserved is True


def test_missing_memory_artifact_blocks_before_runtime_mutation():
    runtime = _runtime()
    snapshot, _ = _snapshot_and_artifacts(runtime)
    runtime.memory.commit(
        MemoryProposal(
            content="drifted memory",
            source_engine="drift",
            confidence=0.95,
            evidence=["restore:drift"],
            trust_class="verified",
            writer="governor",
        )
    )
    before_state = runtime.state
    before_memory = runtime.memory

    with pytest.raises(ValueError, match="memory archive artifact"):
        apply_restore(
            snapshot,
            runtime,
            target_engine="engine-b",
            memory_factory=InMemoryMemoryPort,
        )

    assert runtime.state is before_state
    assert runtime.memory is before_memory
    assert runtime.state.active_engine == "engine-a"


def test_wrong_memory_artifact_digest_blocks_before_runtime_mutation():
    runtime = _runtime()
    snapshot, artifacts = _snapshot_and_artifacts(runtime)
    runtime.memory.commit(
        MemoryProposal(
            content="drifted memory",
            source_engine="drift",
            confidence=0.95,
            evidence=["restore:drift"],
            trust_class="verified",
            writer="governor",
        )
    )
    bad_archive = dict(artifacts.memory_archive)
    bad_archive["records_sha256"] = "0" * 64

    with pytest.raises(ValueError, match="checksum mismatch|digest"):
        apply_restore(
            snapshot,
            runtime,
            target_engine="engine-b",
            artifacts=RestoreArtifacts(
                memory_archive=bad_archive,
                ego_manifests=artifacts.ego_manifests,
            ),
            memory_factory=InMemoryMemoryPort,
        )

    assert runtime.state.active_engine == "engine-a"
    assert len(runtime.memory.all()) == 2


def test_restore_report_can_be_persisted(tmp_path):
    runtime = _runtime()
    snapshot, _ = _snapshot_and_artifacts(runtime)

    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
    )
    path = write_restore_report(report, tmp_path / "restore-report.json")
    envelope = json.loads(path.read_text(encoding="utf-8"))
    payload = load_restore_report(path)

    assert envelope["restore_report_schema_version"] == 1
    assert len(envelope["payload_sha256"]) == 64
    assert payload["status"] == "applied"
    assert payload["continuity_preserved"] is True
    assert payload["target_engine"] == "engine-b"
    assert payload["evidence"]["memory_record_count"] == 1
    assert payload["evidence"]["source_snapshot_sha256"]
    assert payload["evidence"]["post_memory_sha256"]
    assert payload["evidence"]["post_ego_registry_sha256"]


def test_restore_report_tampering_is_detected(tmp_path):
    runtime = _runtime()
    snapshot, _ = _snapshot_and_artifacts(runtime)
    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
    )
    path = write_restore_report(report, tmp_path / "restore-report.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["target_engine"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_restore_report(path)


def test_restore_report_rejects_non_continuity_claim_even_with_valid_checksum(tmp_path):
    import hashlib

    runtime = _runtime()
    snapshot, _ = _snapshot_and_artifacts(runtime)
    report = apply_restore(
        snapshot,
        runtime,
        target_engine="engine-b",
    )
    path = write_restore_report(report, tmp_path / "restore-report.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["continuity_preserved"] = False
    encoded = json.dumps(
        raw["payload"],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    raw["payload_sha256"] = hashlib.sha256(encoded).hexdigest()
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="does not prove continuity"):
        load_restore_report(path)
