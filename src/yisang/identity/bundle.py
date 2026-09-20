from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
import json

from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.library.archive import (
    build_library_archive,
    validate_library_archive,
)
from yisang.library.port import LibraryPort
from yisang.memory.port import MemoryPort
from yisang.memory.transfer import build_memory_archive, validate_memory_archive

from .restore import RestoreArtifacts, RestoreReport, apply_restore
from .snapshot import (
    IdentitySnapshot,
    SnapshotReference,
    _is_authoritative_library_reference,
    build_identity_snapshot,
    ego_registry_digest,
    identity_snapshot_from_dict,
)

CONTINUITY_BUNDLE_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class ContinuityBundle:
    snapshot: IdentitySnapshot
    memory_archive: dict[str, Any]
    ego_manifests: tuple[EgoManifest, ...]
    library_archive: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = {
            "snapshot": self.snapshot.to_dict(),
            "memory_archive": self.memory_archive,
            "ego_manifests": [
                {
                    "ego_id": ego.ego_id,
                    "name": ego.name,
                    "provides": list(ego.provides),
                    "keywords": list(ego.keywords),
                    "instructions": ego.instructions,
                    "permissions": dict(ego.permissions),
                }
                for ego in self.ego_manifests
            ],
        }
        if self.library_archive is not None:
            payload["library_archive"] = self.library_archive
        return payload


def build_continuity_bundle(
    runtime,
    *,
    policy_version: str,
    runtime_version: str,
    library: SnapshotReference | None = None,
) -> ContinuityBundle:
    if library is None:
        snapshot = build_identity_snapshot(
            runtime,
            policy_version=policy_version,
            runtime_version=runtime_version,
        )
    else:
        snapshot = build_identity_snapshot(
            runtime,
            policy_version=policy_version,
            runtime_version=runtime_version,
            library=library,
        )
    memory_archive = build_memory_archive(runtime.memory)
    library_archive = (
        build_library_archive(runtime.library_port)
        if _is_authoritative_library_reference(snapshot.library)
        and getattr(runtime, "library_port", None) is not None
        else None
    )
    egos = tuple(
        sorted(
            runtime.ego_registry.list_all(),
            key=lambda item: item.ego_id,
        )
    )
    bundle = ContinuityBundle(
        snapshot=snapshot,
        memory_archive=memory_archive,
        ego_manifests=egos,
        library_archive=library_archive,
    )
    validate_continuity_bundle(bundle)
    return bundle


def validate_continuity_bundle(bundle: ContinuityBundle) -> None:
    if bundle.snapshot.memory.kind != "memory":
        raise ValueError("continuity bundle snapshot memory reference kind is invalid")
    if bundle.snapshot.ego_registry.kind != "ego_registry":
        raise ValueError("continuity bundle snapshot E.G.O reference kind is invalid")
    if bundle.snapshot.memory.sha256 is None:
        raise ValueError("continuity bundle snapshot memory reference lacks sha256")
    if bundle.snapshot.ego_registry.sha256 is None:
        raise ValueError("continuity bundle snapshot E.G.O reference lacks sha256")

    validate_memory_archive(bundle.memory_archive)

    archive_memory_schema = bundle.memory_archive.get("memory_schema_version")
    if (
        bundle.snapshot.memory.schema_version is not None
        and archive_memory_schema != bundle.snapshot.memory.schema_version
    ):
        raise ValueError(
            "continuity bundle memory schema does not match snapshot reference"
        )

    if bundle.memory_archive.get("records_sha256") != bundle.snapshot.memory.sha256:
        raise ValueError(
            "continuity bundle memory archive does not match snapshot reference"
        )

    registry = EgoRegistry()
    for manifest in bundle.ego_manifests:
        registry.register(manifest)

    if (
        bundle.snapshot.ego_registry.schema_version is not None
        and bundle.snapshot.ego_registry.schema_version != 1
    ):
        raise ValueError(
            "unsupported continuity bundle E.G.O registry schema"
        )

    if ego_registry_digest(registry) != bundle.snapshot.ego_registry.sha256:
        raise ValueError(
            "continuity bundle E.G.O manifests do not match snapshot reference"
        )

    if bundle.snapshot.library is None:
        if bundle.library_archive is not None:
            raise ValueError(
                "continuity bundle Library archive has no snapshot reference"
            )
    else:
        if bundle.snapshot.library.kind != "library":
            raise ValueError(
                "continuity bundle snapshot Library reference kind is invalid"
            )
        if _is_authoritative_library_reference(bundle.snapshot.library):
            if bundle.snapshot.library.sha256 is None:
                raise ValueError(
                    "continuity bundle snapshot Library reference lacks sha256"
                )
            if bundle.library_archive is None:
                raise ValueError(
                    "continuity bundle snapshot requires library_archive"
                )
            validate_library_archive(bundle.library_archive)
            archive_library_schema = bundle.library_archive.get(
                "library_schema_version"
            )
            if (
                bundle.snapshot.library.schema_version is not None
                and archive_library_schema != bundle.snapshot.library.schema_version
            ):
                raise ValueError(
                    "continuity bundle Library schema does not match snapshot reference"
                )
            if (
                bundle.library_archive.get("books_sha256")
                != bundle.snapshot.library.sha256
            ):
                raise ValueError(
                    "continuity bundle Library archive does not match snapshot reference"
                )
        elif bundle.library_archive is not None:
            raise ValueError(
                "reference-only Library snapshots must not carry library_archive"
            )


def write_continuity_bundle(
    bundle: ContinuityBundle,
    path: str | Path,
) -> Path:
    validate_continuity_bundle(bundle)
    payload = bundle.to_payload()
    envelope = {
        "bundle_schema_version": CONTINUITY_BUNDLE_SCHEMA_VERSION,
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


def load_continuity_bundle(path: str | Path) -> ContinuityBundle:
    try:
        envelope = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("continuity bundle is not valid JSON") from exc

    if not isinstance(envelope, dict):
        raise ValueError("continuity bundle envelope must be an object")
    if envelope.get("bundle_schema_version") != CONTINUITY_BUNDLE_SCHEMA_VERSION:
        raise ValueError("unsupported continuity bundle schema")

    payload = envelope.get("payload")
    if not isinstance(payload, dict):
        raise ValueError("continuity bundle payload must be an object")

    expected = envelope.get("payload_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("continuity bundle payload_sha256 is invalid")
    if _sha256_json(payload) != expected:
        raise ValueError("continuity bundle checksum mismatch")

    snapshot_raw = payload.get("snapshot")
    memory_archive = payload.get("memory_archive")
    ego_raw = payload.get("ego_manifests")
    library_archive = payload.get("library_archive")

    if not isinstance(snapshot_raw, dict):
        raise ValueError("continuity bundle snapshot must be an object")
    if not isinstance(memory_archive, dict):
        raise ValueError("continuity bundle memory_archive must be an object")
    if not isinstance(ego_raw, list):
        raise ValueError("continuity bundle ego_manifests must be a list")
    if library_archive is not None and not isinstance(library_archive, dict):
        raise ValueError("continuity bundle library_archive must be an object")

    snapshot = identity_snapshot_from_dict(snapshot_raw)
    egos = tuple(_ego_from_dict(item) for item in ego_raw)

    bundle = ContinuityBundle(
        snapshot=snapshot,
        memory_archive=dict(memory_archive),
        ego_manifests=egos,
        library_archive=(
            dict(library_archive)
            if library_archive is not None
            else None
        ),
    )
    validate_continuity_bundle(bundle)
    return bundle


def restore_continuity_bundle(
    bundle: ContinuityBundle,
    runtime,
    *,
    target_engine: str,
    memory_factory: Callable[[], MemoryPort] | None = None,
    library_factory: Callable[[], LibraryPort] | None = None,
) -> RestoreReport:
    validate_continuity_bundle(bundle)
    return apply_restore(
        bundle.snapshot,
        runtime,
        target_engine=target_engine,
        artifacts=RestoreArtifacts(
            memory_archive=bundle.memory_archive,
            ego_manifests=bundle.ego_manifests,
            library_archive=bundle.library_archive,
        ),
        memory_factory=memory_factory,
        library_factory=library_factory,
    )


def _ego_from_dict(raw: Any) -> EgoManifest:
    if not isinstance(raw, dict):
        raise ValueError("E.G.O manifest must be an object")

    provides = raw.get("provides", [])
    keywords = raw.get("keywords", [])
    permissions = raw.get("permissions", {})

    if not isinstance(provides, list):
        raise ValueError("E.G.O provides must be a list")
    if not isinstance(keywords, list):
        raise ValueError("E.G.O keywords must be a list")
    if not isinstance(permissions, dict):
        raise ValueError("E.G.O permissions must be an object")

    return EgoManifest(
        ego_id=str(raw["ego_id"]),
        name=str(raw["name"]),
        provides=tuple(str(item) for item in provides),
        keywords=tuple(str(item) for item in keywords),
        instructions=str(raw.get("instructions", "")),
        permissions=dict(permissions),
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
