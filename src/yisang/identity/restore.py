from __future__ import annotations

from dataclasses import asdict, dataclass, field
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import json
import time

from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.port import MemoryPort
from yisang.memory.transfer import (
    build_memory_archive,
    restore_memory_archive,
    validate_memory_archive,
)

from .snapshot import (
    IdentitySnapshot,
    build_identity_snapshot,
    continuity_fingerprint,
    ego_registry_digest,
    snapshot_payload_sha256,
    validate_identity_snapshot,
    validate_snapshot_against_runtime,
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


@dataclass(frozen=True)
class RestoreArtifacts:
    memory_archive: dict | None = None
    ego_manifests: tuple[EgoManifest, ...] | None = None


@dataclass(frozen=True)
class RestoreReport:
    snapshot_id: str
    target_engine: str
    status: str
    applied_at: float
    identity_restored: bool
    state_restored: bool
    memory_restored: bool
    ego_registry_restored: bool
    pre_continuity_fingerprint: str
    post_continuity_fingerprint: str
    warnings: tuple[str, ...] = ()
    evidence: dict[str, str | int | bool | None] = field(default_factory=dict)

    @property
    def continuity_preserved(self) -> bool:
        return (
            self.status == "applied"
            and self.pre_continuity_fingerprint
            == self.post_continuity_fingerprint
        )

    def to_dict(self) -> dict:
        return {
            **asdict(self),
            "continuity_preserved": self.continuity_preserved,
        }


RESTORE_REPORT_SCHEMA_VERSION = 1

MemoryFactory = Callable[[], MemoryPort]


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


def apply_restore(
    snapshot: IdentitySnapshot,
    runtime,
    *,
    target_engine: str,
    artifacts: RestoreArtifacts | None = None,
    memory_factory: MemoryFactory | None = None,
) -> RestoreReport:
    """Stage, validate, then atomically swap runtime continuity components.

    No runtime-owned state is mutated until all required restore artifacts are
    validated and staged successfully.
    """
    plan = plan_restore(snapshot, runtime, target_engine=target_engine)
    if plan.blockers:
        raise ValueError(
            "restore blocked: " + "; ".join(plan.blockers)
        )

    artifacts = artifacts or RestoreArtifacts()
    staged_identity = identity_from_snapshot(snapshot)
    staged_state = state_from_snapshot(
        snapshot,
        active_engine=target_engine,
    )

    staged_memory = runtime.memory
    if plan.requires_memory_restore:
        if artifacts.memory_archive is None:
            raise ValueError(
                "restore requires a memory archive artifact"
            )
        if memory_factory is None:
            raise ValueError(
                "restore requires memory_factory when authoritative memory differs"
            )
        validate_memory_archive(artifacts.memory_archive)
        if artifacts.memory_archive.get("records_sha256") != snapshot.memory.sha256:
            raise ValueError(
                "memory archive digest does not match snapshot reference"
            )

        candidate_memory = memory_factory()
        if candidate_memory.all():
            raise ValueError(
                "memory_factory must return an empty staging MemoryPort"
            )
        restore_memory_archive(
            candidate_memory,
            artifacts.memory_archive,
            overwrite=False,
        )
        staged_archive = build_memory_archive(candidate_memory)
        if staged_archive["records_sha256"] != snapshot.memory.sha256:
            raise ValueError(
                "staged memory digest does not match snapshot reference"
            )
        staged_memory = candidate_memory

    staged_egos = runtime.ego_registry
    if plan.requires_ego_restore:
        if artifacts.ego_manifests is None:
            raise ValueError(
                "restore requires E.G.O manifest artifacts"
            )
        candidate_egos = EgoRegistry()
        for manifest in artifacts.ego_manifests:
            candidate_egos.register(manifest)
        if ego_registry_digest(candidate_egos) != snapshot.ego_registry.sha256:
            raise ValueError(
                "staged E.G.O registry digest does not match snapshot reference"
            )
        staged_egos = candidate_egos

    restore_started_at = time.time()
    pre_snapshot = build_identity_snapshot(
        runtime,
        policy_version=snapshot.policy_version,
        runtime_version=snapshot.runtime_version,
        library=snapshot.library,
    )
    pre_fingerprint = continuity_fingerprint(snapshot)

    old_identity = runtime.identity
    old_state = runtime.state
    old_memory = runtime.memory
    old_egos = runtime.ego_registry
    old_pipeline = runtime.memory_pipeline

    try:
        runtime.identity = staged_identity
        runtime.state = staged_state
        runtime.memory = staged_memory
        runtime.ego_registry = staged_egos

        # Keep the existing governor/quarantine object identities but redirect
        # governed writes to the staged authoritative store.
        runtime.memory_pipeline = MemoryWritePipeline(
            memory=staged_memory,
            governor=runtime.governor,
            quarantine=runtime.memory_pipeline.quarantine,
        )

        validation = validate_snapshot_against_runtime(snapshot, runtime)
        if not validation.valid:
            raise ValueError(
                "post-restore validation failed: "
                + "; ".join(validation.errors)
            )

        post_snapshot = build_identity_snapshot(
            runtime,
            policy_version=snapshot.policy_version,
            runtime_version=snapshot.runtime_version,
            library=snapshot.library,
        )
        post_fingerprint = continuity_fingerprint(post_snapshot)
        if post_fingerprint != pre_fingerprint:
            raise ValueError(
                "post-restore continuity fingerprint does not match snapshot"
            )
    except Exception:
        runtime.identity = old_identity
        runtime.state = old_state
        runtime.memory = old_memory
        runtime.ego_registry = old_egos
        runtime.memory_pipeline = old_pipeline
        raise

    return RestoreReport(
        snapshot_id=snapshot.snapshot_id,
        target_engine=target_engine,
        status="applied",
        applied_at=time.time(),
        identity_restored=not plan.identity_matches,
        state_restored=plan.requires_state_restore,
        memory_restored=plan.requires_memory_restore,
        ego_registry_restored=plan.requires_ego_restore,
        pre_continuity_fingerprint=pre_fingerprint,
        post_continuity_fingerprint=post_fingerprint,
        warnings=plan.warnings,
        evidence={
            "memory_record_count": len(runtime.memory.all()),
            "ego_count": len(runtime.ego_registry.list_all()),
            "memory_sha256": snapshot.memory.sha256,
            "ego_registry_sha256": snapshot.ego_registry.sha256,
            "target_engine_registered": True,
            "source_snapshot_sha256": snapshot_payload_sha256(snapshot),
            "pre_runtime_snapshot_id": pre_snapshot.snapshot_id,
            "post_runtime_snapshot_id": post_snapshot.snapshot_id,
            "post_memory_sha256": post_snapshot.memory.sha256,
            "post_ego_registry_sha256": post_snapshot.ego_registry.sha256,
            "restore_started_at": restore_started_at,
        },
    )


def restore_report_sha256(report: RestoreReport) -> str:
    return _sha256_json(report.to_dict())


def write_restore_report(
    report: RestoreReport,
    path: str | Path,
) -> Path:
    payload = report.to_dict()
    envelope = {
        "restore_report_schema_version": RESTORE_REPORT_SCHEMA_VERSION,
        "payload_sha256": _sha256_json(payload),
        "payload": payload,
    }
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            envelope,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def load_restore_report(path: str | Path) -> dict[str, Any]:
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("restore report is not valid JSON") from exc

    if not isinstance(envelope, dict):
        raise ValueError("restore report envelope must be an object")
    if envelope.get("restore_report_schema_version") != RESTORE_REPORT_SCHEMA_VERSION:
        raise ValueError("unsupported restore report schema")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("restore report payload must be an object")

    expected = envelope.get("payload_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("restore report payload_sha256 is invalid")
    if _sha256_json(payload) != expected:
        raise ValueError("restore report checksum mismatch")

    if payload.get("status") != "applied":
        raise ValueError("restore report status is not applied")
    if payload.get("continuity_preserved") is not True:
        raise ValueError("restore report does not prove continuity preservation")

    return payload


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


def _sha256_json(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()
