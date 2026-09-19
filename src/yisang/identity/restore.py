from __future__ import annotations

from dataclasses import dataclass

from yisang.identity.models import AgentState, IdentityCharter

from .snapshot import (
    IdentitySnapshot,
    build_identity_snapshot,
    validate_identity_snapshot,
)


@dataclass(frozen=True)
class RestorePlan:
    snapshot_id: str
    target_engine: str
    identity_matches: bool
    memory_matches: bool
    ego_registry_matches: bool
    state_matches: bool
    requires_memory_restore: bool
    requires_ego_restore: bool
    requires_state_restore: bool
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]

    @property
    def can_apply_identity_state(self) -> bool:
        return not self.blockers


def plan_restore(
    snapshot: IdentitySnapshot,
    runtime,
    *,
    target_engine: str,
) -> RestorePlan:
    structural = validate_identity_snapshot(snapshot)
    blockers = list(structural.errors)
    warnings = list(structural.warnings)

    try:
        runtime.engine_router.get(target_engine)
    except KeyError:
        blockers.append(f"target engine is not registered: {target_engine}")

    current = build_identity_snapshot(
        runtime,
        policy_version=snapshot.policy_version,
        runtime_version=snapshot.runtime_version,
        library=snapshot.library,
    )

    identity_matches = current.agent_id == snapshot.agent_id
    memory_matches = current.memory == snapshot.memory
    ego_matches = current.ego_registry == snapshot.ego_registry
    state_matches = current.state == snapshot.state

    if not identity_matches:
        blockers.append("runtime identity does not match snapshot agent_id")
    if not memory_matches:
        warnings.append("authoritative memory restore is required")
    if not ego_matches:
        warnings.append("E.G.O registry restore is required")
    if not state_matches:
        warnings.append("engine-independent state restore is required")

    return RestorePlan(
        snapshot_id=snapshot.snapshot_id,
        target_engine=target_engine,
        identity_matches=identity_matches,
        memory_matches=memory_matches,
        ego_registry_matches=ego_matches,
        state_matches=state_matches,
        requires_memory_restore=not memory_matches,
        requires_ego_restore=not ego_matches,
        requires_state_restore=not state_matches,
        blockers=tuple(blockers),
        warnings=tuple(dict.fromkeys(warnings)),
    )


def identity_from_snapshot(snapshot: IdentitySnapshot) -> IdentityCharter:
    report = validate_identity_snapshot(snapshot)
    if not report.valid:
        raise ValueError(
            "cannot reconstruct identity from invalid snapshot: "
            + "; ".join(report.errors)
        )
    principles = snapshot.identity.get("principles", [])
    if not isinstance(principles, list):
        raise ValueError("snapshot identity principles must be a list")
    return IdentityCharter(
        agent_id=snapshot.agent_id,
        name=str(snapshot.identity.get("name", "")),
        principles=tuple(str(item) for item in principles),
    )


def state_from_snapshot(
    snapshot: IdentitySnapshot,
    *,
    active_engine: str,
) -> AgentState:
    if not active_engine.strip():
        raise ValueError("active_engine must be non-empty")
    report = validate_identity_snapshot(snapshot)
    if not report.valid:
        raise ValueError(
            "cannot reconstruct state from invalid snapshot: "
            + "; ".join(report.errors)
        )

    tags = snapshot.state.get("tags", {})
    if not isinstance(tags, dict):
        raise ValueError("snapshot state tags must be an object")

    return AgentState(
        active_engine=active_engine,
        active_project=(
            str(snapshot.state["active_project"])
            if snapshot.state.get("active_project") is not None
            else None
        ),
        current_goal=(
            str(snapshot.state["current_goal"])
            if snapshot.state.get("current_goal") is not None
            else None
        ),
        tags={str(key): str(value) for key, value in tags.items()},
    )
