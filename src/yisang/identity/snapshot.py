from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any
import json
import time
import uuid

from yisang.memory.models import MEMORY_SCHEMA_VERSION
from yisang.memory.transfer import build_memory_archive

SNAPSHOT_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class SnapshotReference:
    kind: str
    ref: str
    sha256: str | None = None
    schema_version: int | None = None

    def __post_init__(self) -> None:
        if not self.kind.strip():
            raise ValueError("reference kind must be non-empty")
        if not self.ref.strip():
            raise ValueError("reference ref must be non-empty")
        if self.sha256 is not None and len(self.sha256) != 64:
            raise ValueError("reference sha256 must be 64 hex characters")
        if self.schema_version is not None and self.schema_version <= 0:
            raise ValueError("reference schema_version must be positive")


@dataclass(frozen=True)
class MigrationRecord:
    migration_id: str
    from_version: int
    to_version: int
    applied_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.migration_id.strip():
            raise ValueError("migration_id must be non-empty")
        if self.from_version <= 0 or self.to_version <= 0:
            raise ValueError("migration versions must be positive")
        if self.to_version < self.from_version:
            raise ValueError("migration to_version must be >= from_version")


@dataclass(frozen=True)
class IdentitySnapshot:
    snapshot_id: str
    agent_id: str
    identity: dict[str, Any]
    state: dict[str, Any]
    active_goals: tuple[str, ...]
    memory: SnapshotReference
    ego_registry: SnapshotReference
    library: SnapshotReference | None
    policy_version: str
    runtime_version: str
    migrations: tuple[MigrationRecord, ...] = ()
    schema_version: int = SNAPSHOT_SCHEMA_VERSION
    created_at: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.snapshot_id.strip():
            raise ValueError("snapshot_id must be non-empty")
        if not self.agent_id.strip():
            raise ValueError("agent_id must be non-empty")
        if not self.policy_version.strip():
            raise ValueError("policy_version must be non-empty")
        if not self.runtime_version.strip():
            raise ValueError("runtime_version must be non-empty")
        if self.schema_version <= 0:
            raise ValueError("schema_version must be positive")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["active_goals"] = list(self.active_goals)
        payload["migrations"] = [asdict(item) for item in self.migrations]
        return payload


@dataclass(frozen=True)
class SnapshotValidationReport:
    valid: bool
    errors: tuple[str, ...]
    warnings: tuple[str, ...] = ()


def build_identity_snapshot(
    runtime,
    *,
    policy_version: str,
    runtime_version: str,
    library: SnapshotReference | None = None,
    migrations: tuple[MigrationRecord, ...] = (),
) -> IdentitySnapshot:
    memory_archive = build_memory_archive(runtime.memory)
    ego_payload = ego_registry_payload(runtime.ego_registry)

    goal = runtime.state.current_goal
    active_goals = (goal,) if isinstance(goal, str) and goal.strip() else ()

    # active_engine is intentionally excluded: the engine is replaceable and
    # must not be part of the persistent identity state.
    state = {
        "active_project": runtime.state.active_project,
        "current_goal": runtime.state.current_goal,
        "tags": dict(runtime.state.tags),
    }

    return IdentitySnapshot(
        snapshot_id=f"ysnap-{uuid.uuid4().hex[:12]}",
        agent_id=runtime.identity.agent_id,
        identity={
            "agent_id": runtime.identity.agent_id,
            "name": runtime.identity.name,
            "principles": list(runtime.identity.principles),
        },
        state=state,
        active_goals=active_goals,
        memory=SnapshotReference(
            kind="memory",
            ref="memory://authoritative",
            sha256=memory_archive["records_sha256"],
            schema_version=MEMORY_SCHEMA_VERSION,
        ),
        ego_registry=SnapshotReference(
            kind="ego_registry",
            ref="ego://registry",
            sha256=_sha256_json(ego_payload),
            schema_version=1,
        ),
        library=library,
        policy_version=policy_version,
        runtime_version=runtime_version,
        migrations=tuple(migrations),
    )


def snapshot_payload_sha256(snapshot: IdentitySnapshot) -> str:
    return _sha256_json(snapshot.to_dict())


def continuity_fingerprint(snapshot: IdentitySnapshot) -> str:
    """Hash persistent agent state while excluding capture-instance metadata.

    snapshot_id, created_at, runtime_version and any replaceable engine id are
    intentionally outside the continuity identity.
    """
    payload = {
        "agent_id": snapshot.agent_id,
        "identity": snapshot.identity,
        "state": snapshot.state,
        "active_goals": list(snapshot.active_goals),
        "memory": asdict(snapshot.memory),
        "ego_registry": asdict(snapshot.ego_registry),
        "library": asdict(snapshot.library) if snapshot.library else None,
        "policy_version": snapshot.policy_version,
        "schema_version": snapshot.schema_version,
        "migrations": [asdict(item) for item in snapshot.migrations],
    }
    return _sha256_json(payload)


def write_identity_snapshot(
    snapshot: IdentitySnapshot,
    path: str | Path,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = snapshot.to_dict()
    envelope = {
        "snapshot_schema_version": SNAPSHOT_SCHEMA_VERSION,
        "payload_sha256": _sha256_json(payload),
        "payload": payload,
    }
    output.write_text(
        json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def load_identity_snapshot(path: str | Path) -> IdentitySnapshot:
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("identity snapshot is not valid JSON") from exc
    if not isinstance(envelope, dict):
        raise ValueError("identity snapshot envelope must be an object")
    if envelope.get("snapshot_schema_version") != SNAPSHOT_SCHEMA_VERSION:
        raise ValueError("unsupported identity snapshot schema")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("identity snapshot payload must be an object")
    expected = envelope.get("payload_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("identity snapshot payload_sha256 is invalid")
    if _sha256_json(payload) != expected:
        raise ValueError("identity snapshot checksum mismatch")

    snapshot = _snapshot_from_dict(payload)
    report = validate_identity_snapshot(snapshot)
    if not report.valid:
        raise ValueError(
            "identity snapshot validation failed: " + "; ".join(report.errors)
        )
    return snapshot


def validate_identity_snapshot(
    snapshot: IdentitySnapshot,
) -> SnapshotValidationReport:
    errors: list[str] = []
    warnings: list[str] = []

    if snapshot.schema_version != SNAPSHOT_SCHEMA_VERSION:
        errors.append(
            f"snapshot schema={snapshot.schema_version}, "
            f"supported={SNAPSHOT_SCHEMA_VERSION}"
        )
    if snapshot.identity.get("agent_id") != snapshot.agent_id:
        errors.append("identity agent_id does not match snapshot agent_id")
    if snapshot.state.get("current_goal") is None and snapshot.active_goals:
        errors.append("active_goals present while current_goal is empty")
    if snapshot.state.get("current_goal") is not None:
        goal = str(snapshot.state["current_goal"])
        if goal not in snapshot.active_goals:
            errors.append("current_goal is missing from active_goals")
    if "active_engine" in snapshot.state:
        errors.append("replaceable active_engine must not be snapshot-authoritative")
    if snapshot.library is None:
        warnings.append("library reference not configured yet")

    return SnapshotValidationReport(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def validate_snapshot_against_runtime(
    snapshot: IdentitySnapshot,
    runtime,
) -> SnapshotValidationReport:
    base = validate_identity_snapshot(snapshot)
    errors = list(base.errors)
    warnings = list(base.warnings)

    if runtime.identity.agent_id != snapshot.agent_id:
        errors.append("runtime agent_id does not match snapshot")

    memory_archive = build_memory_archive(runtime.memory)
    if snapshot.memory.sha256 != memory_archive["records_sha256"]:
        errors.append("authoritative memory digest does not match snapshot")

    ego_digest = ego_registry_digest(runtime.ego_registry)
    if snapshot.ego_registry.sha256 != ego_digest:
        errors.append("E.G.O registry digest does not match snapshot")

    runtime_state = {
        "active_project": runtime.state.active_project,
        "current_goal": runtime.state.current_goal,
        "tags": dict(runtime.state.tags),
    }
    if runtime_state != snapshot.state:
        errors.append("engine-independent runtime state does not match snapshot")

    return SnapshotValidationReport(
        valid=not errors,
        errors=tuple(errors),
        warnings=tuple(warnings),
    )


def ego_registry_payload(registry) -> list[dict[str, Any]]:
    return [
        {
            "ego_id": ego.ego_id,
            "name": ego.name,
            "provides": list(ego.provides),
            "keywords": list(ego.keywords),
            "instructions": ego.instructions,
            "permissions": dict(ego.permissions),
        }
        for ego in sorted(
            registry.list_all(),
            key=lambda item: item.ego_id,
        )
    ]


def ego_registry_digest(registry) -> str:
    return _sha256_json(ego_registry_payload(registry))


def _snapshot_from_dict(raw: dict[str, Any]) -> IdentitySnapshot:
    memory = _reference_from_dict(raw.get("memory"), "memory")
    ego_registry = _reference_from_dict(
        raw.get("ego_registry"),
        "ego_registry",
    )
    library_raw = raw.get("library")
    library = (
        _reference_from_dict(library_raw, "library")
        if library_raw is not None
        else None
    )

    migration_raw = raw.get("migrations", [])
    if not isinstance(migration_raw, list):
        raise ValueError("snapshot migrations must be a list")
    migrations = tuple(
        MigrationRecord(
            migration_id=str(item["migration_id"]),
            from_version=int(item["from_version"]),
            to_version=int(item["to_version"]),
            applied_at=float(item.get("applied_at", 0.0)),
        )
        for item in migration_raw
        if isinstance(item, dict)
    )

    identity = raw.get("identity")
    state = raw.get("state")
    active_goals = raw.get("active_goals", [])
    if not isinstance(identity, dict) or not isinstance(state, dict):
        raise ValueError("snapshot identity/state must be objects")
    if not isinstance(active_goals, list):
        raise ValueError("snapshot active_goals must be a list")

    return IdentitySnapshot(
        snapshot_id=str(raw["snapshot_id"]),
        agent_id=str(raw["agent_id"]),
        identity=dict(identity),
        state=dict(state),
        active_goals=tuple(str(item) for item in active_goals),
        memory=memory,
        ego_registry=ego_registry,
        library=library,
        policy_version=str(raw["policy_version"]),
        runtime_version=str(raw["runtime_version"]),
        migrations=migrations,
        schema_version=int(raw.get("schema_version", SNAPSHOT_SCHEMA_VERSION)),
        created_at=float(raw.get("created_at", 0.0)),
    )


def _reference_from_dict(raw: Any, name: str) -> SnapshotReference:
    if not isinstance(raw, dict):
        raise ValueError(f"snapshot {name} reference must be an object")
    return SnapshotReference(
        kind=str(raw["kind"]),
        ref=str(raw["ref"]),
        sha256=str(raw["sha256"]) if raw.get("sha256") is not None else None,
        schema_version=(
            int(raw["schema_version"])
            if raw.get("schema_version") is not None
            else None
        ),
    )


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
