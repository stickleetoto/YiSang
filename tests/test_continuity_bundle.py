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
    build_continuity_bundle,
    continuity_fingerprint,
    load_continuity_bundle,
    restore_continuity_bundle,
    write_continuity_bundle,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _runtime(*, with_state=True):
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()
    engines = EngineRouter()
    engines.register(EchoEngine("engine-a", "A"))
    engines.register(EchoEngine("engine-b", "B"))

    if with_state:
        memory.commit(
            MemoryProposal(
                content="bundle continuity memory",
                source_engine="seed",
                confidence=0.95,
                evidence=["bundle:seed"],
                trust_class="verified",
                writer="governor",
            )
        )
        egos.register(
            EgoManifest(
                ego_id="ego.debug",
                name="Debug",
                provides=("debug",),
                keywords=("bug",),
                instructions="Inspect evidence before changing state.",
            )
        )
        state = AgentState(
            active_engine="engine-a",
            active_project="YiSang",
            current_goal="restore from portable bundle",
            tags={"phase": "v0.5"},
        )
    else:
        state = AgentState(active_engine="engine-a")

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=state,
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )


def test_continuity_bundle_round_trip(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )

    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    loaded = load_continuity_bundle(path)

    assert loaded.snapshot.agent_id == "yisang-001"
    assert loaded.memory_archive["record_count"] == 1
    assert [ego.ego_id for ego in loaded.ego_manifests] == ["ego.debug"]
    assert continuity_fingerprint(loaded.snapshot) == continuity_fingerprint(
        bundle.snapshot
    )


def test_continuity_bundle_detects_envelope_tampering(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")

    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["memory_archive"]["records"][0]["content"] = "tampered"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_continuity_bundle(path)


def test_bundle_restore_rehydrates_fresh_runtime_and_swaps_engine():
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )

    target = _runtime(with_state=False)
    report = restore_continuity_bundle(
        bundle,
        target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
    )

    assert report.continuity_preserved is True
    assert report.memory_restored is True
    assert report.ego_registry_restored is True
    assert report.state_restored is True

    assert target.state.active_engine == "engine-b"
    assert target.state.active_project == "YiSang"
    assert target.state.current_goal == "restore from portable bundle"
    assert target.state.tags == {"phase": "v0.5"}
    assert [record.content for record in target.memory.all()] == [
        "bundle continuity memory"
    ]
    assert [ego.ego_id for ego in target.ego_registry.list_all()] == [
        "ego.debug"
    ]


def test_bundle_restore_requires_empty_staging_memory():
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    target = _runtime(with_state=False)

    def dirty_factory():
        memory = InMemoryMemoryPort()
        memory.commit(
            MemoryProposal(
                content="preexisting staging data",
                source_engine="seed",
                confidence=0.95,
                evidence=["dirty"],
                trust_class="verified",
                writer="governor",
            )
        )
        return memory

    with pytest.raises(ValueError, match="empty staging MemoryPort"):
        restore_continuity_bundle(
            bundle,
            target,
            target_engine="engine-b",
            memory_factory=dirty_factory,
        )

    assert target.state.active_engine == "engine-a"
    assert target.memory.all() == []


def test_bundle_rejects_ego_manifest_drift_before_restore(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw["payload"]["ego_manifests"][0]["name"] = "Tampered"
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="E.G.O manifests"):
        load_continuity_bundle(path)


def _payload_sha(payload):
    import hashlib

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def test_bundle_rejects_missing_memory_artifact_after_valid_envelope(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    del raw["payload"]["memory_archive"]
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="memory_archive must be an object"):
        load_continuity_bundle(path)


def test_bundle_rejects_memory_schema_reference_mismatch(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw["payload"]["snapshot"]["memory"]["schema_version"] = 999
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="memory schema"):
        load_continuity_bundle(path)


def test_bundle_rejects_wrong_snapshot_reference_kind(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw["payload"]["snapshot"]["memory"]["kind"] = "library"
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="memory reference kind"):
        load_continuity_bundle(path)


def test_bundle_rejects_duplicate_ego_ids(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw["payload"]["ego_manifests"].append(
        dict(raw["payload"]["ego_manifests"][0])
    )
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate E.G.O id"):
        load_continuity_bundle(path)
