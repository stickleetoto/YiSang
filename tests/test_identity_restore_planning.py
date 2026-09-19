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
    SnapshotMigration,
    SnapshotMigrationRegistry,
    build_identity_snapshot,
    identity_from_snapshot,
    plan_restore,
    state_from_snapshot,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _runtime():
    memory = InMemoryMemoryPort()
    memory.commit(
        MemoryProposal(
            content="restore planning memory",
            source_engine="seed",
            confidence=0.95,
            evidence=["restore:test"],
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
            current_goal="restore continuity",
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


def test_restore_plan_allows_engine_swap_when_persistent_refs_match():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )

    plan = plan_restore(snapshot, runtime, target_engine="engine-b")

    assert plan.can_apply_identity_state is True
    assert plan.memory_matches is True
    assert plan.ego_registry_matches is True
    assert plan.state_matches is True
    assert plan.requires_memory_restore is False
    assert plan.requires_ego_restore is False


def test_restore_plan_detects_missing_target_engine():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )

    plan = plan_restore(snapshot, runtime, target_engine="missing")

    assert plan.can_apply_identity_state is False
    assert any("not registered" in item for item in plan.blockers)


def test_restore_plan_marks_memory_drift_as_required_restore():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )
    runtime.memory.commit(
        MemoryProposal(
            content="new drift",
            source_engine="seed",
            confidence=0.95,
            evidence=["restore:drift"],
            trust_class="verified",
            writer="governor",
        )
    )

    plan = plan_restore(snapshot, runtime, target_engine="engine-b")

    assert plan.requires_memory_restore is True
    assert any("memory restore" in item for item in plan.warnings)


def test_identity_and_state_reconstruction_requires_external_engine_choice():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.5-prep",
    )

    identity = identity_from_snapshot(snapshot)
    state = state_from_snapshot(snapshot, active_engine="engine-b")

    assert identity.agent_id == "yisang-001"
    assert state.active_engine == "engine-b"
    assert state.active_project == "YiSang"
    assert state.current_goal == "restore continuity"
    assert state.tags == {"phase": "v0.5"}


def test_snapshot_migration_registry_plans_and_applies_explicit_chain():
    registry = SnapshotMigrationRegistry()
    registry.register(
        SnapshotMigration(
            migration_id="v1-to-v2",
            from_version=1,
            to_version=2,
            transform=lambda payload: {**payload, "added_v2": True},
        )
    )
    registry.register(
        SnapshotMigration(
            migration_id="v2-to-v3",
            from_version=2,
            to_version=3,
            transform=lambda payload: {**payload, "added_v3": True},
        )
    )

    plan = registry.plan(1, 3)
    migrated, records = registry.apply(
        {"schema_version": 1},
        from_version=1,
        to_version=3,
    )

    assert [item.migration_id for item in plan] == ["v1-to-v2", "v2-to-v3"]
    assert migrated["schema_version"] == 3
    assert migrated["added_v2"] is True
    assert migrated["added_v3"] is True
    assert [item.migration_id for item in records] == ["v1-to-v2", "v2-to-v3"]


def test_snapshot_migration_registry_rejects_missing_path():
    registry = SnapshotMigrationRegistry()

    with pytest.raises(ValueError, match="no snapshot migration path"):
        registry.plan(1, 2)
