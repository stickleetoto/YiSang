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
    build_identity_snapshot,
    continuity_fingerprint,
    load_identity_snapshot,
    validate_identity_snapshot,
    validate_snapshot_against_runtime,
    write_identity_snapshot,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _runtime():
    memory = InMemoryMemoryPort()
    memory.commit(
        MemoryProposal(
            content="persistent snapshot memory",
            source_engine="seed",
            confidence=0.95,
            evidence=["test:snapshot"],
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
            current_goal="v0.5 identity continuity",
            tags={"phase": "prep"},
        ),
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
    )


def test_snapshot_excludes_replaceable_engine_from_authoritative_state():
    runtime = _runtime()

    snapshot = build_identity_snapshot(
        runtime,
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )

    assert snapshot.agent_id == "yisang-001"
    assert "active_engine" not in snapshot.state
    assert snapshot.state["active_project"] == "YiSang"
    assert snapshot.active_goals == ("v0.5 identity continuity",)
    assert snapshot.memory.sha256
    assert snapshot.ego_registry.sha256


def test_engine_swap_does_not_change_continuity_fingerprint():
    runtime = _runtime()
    before = build_identity_snapshot(
        runtime,
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )

    runtime.state.active_engine = "engine-b"

    after = build_identity_snapshot(
        runtime,
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )

    assert before.snapshot_id != after.snapshot_id
    assert continuity_fingerprint(before) == continuity_fingerprint(after)


def test_snapshot_write_load_round_trip_and_checksum(tmp_path):
    snapshot = build_identity_snapshot(
        _runtime(),
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )
    path = write_identity_snapshot(snapshot, tmp_path / "snapshot.json")

    loaded = load_identity_snapshot(path)

    assert loaded.agent_id == snapshot.agent_id
    assert loaded.memory == snapshot.memory
    assert loaded.ego_registry == snapshot.ego_registry
    assert continuity_fingerprint(loaded) == continuity_fingerprint(snapshot)


def test_snapshot_tampering_is_detected(tmp_path):
    snapshot = build_identity_snapshot(
        _runtime(),
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )
    path = write_identity_snapshot(snapshot, tmp_path / "snapshot.json")
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["payload"]["state"]["current_goal"] = "tampered goal"
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        load_identity_snapshot(path)


def test_snapshot_validation_rejects_engine_as_authoritative_state():
    snapshot = build_identity_snapshot(
        _runtime(),
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )
    object.__setattr__(
        snapshot,
        "state",
        {**snapshot.state, "active_engine": "engine-a"},
    )

    report = validate_identity_snapshot(snapshot)

    assert report.valid is False
    assert any("active_engine" in error for error in report.errors)


def test_snapshot_runtime_validation_ignores_engine_swap_but_detects_state_drift():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="memory-governance-v1",
        runtime_version="0.5-prep",
    )

    runtime.state.active_engine = "engine-b"
    after_swap = validate_snapshot_against_runtime(snapshot, runtime)
    assert after_swap.valid is True

    runtime.state.current_goal = "different goal"
    drifted = validate_snapshot_against_runtime(snapshot, runtime)
    assert drifted.valid is False
    assert any("state" in error for error in drifted.errors)
