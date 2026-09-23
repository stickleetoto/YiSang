from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
from typing import Any

from .models import (
    EGO_PACKAGE_SCHEMA_VERSION,
    JSON_SCHEMA_2020_12,
    EgoManifest,
    EgoRiskHints,
)


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)


@dataclass(frozen=True)
class EgoPackageDescriptor:
    root: Path
    manifest_path: Path
    summary: EgoManifest
    instructions_file: str
    input_schema_file: str | None
    output_schema_file: str | None

    def load(self) -> EgoManifest:
        return load_ego_package(self.root)


def discover_ego_packages(root: str | Path) -> list[EgoPackageDescriptor]:
    root_path = Path(root)
    if not root_path.exists():
        raise FileNotFoundError(root_path)

    descriptors: list[EgoPackageDescriptor] = []
    for manifest_path in sorted(root_path.rglob("manifest.json")):
        data = _read_manifest(manifest_path)
        if int(data.get("schema_version", 1)) < EGO_PACKAGE_SCHEMA_VERSION:
            continue
        descriptors.append(_descriptor_from_data(manifest_path, data))
    return descriptors


def load_ego_package(root: str | Path) -> EgoManifest:
    package_root = Path(root)
    manifest_path = package_root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    data = _read_manifest(manifest_path)
    descriptor = _descriptor_from_data(manifest_path, data)

    instruction_path = _safe_file(package_root, descriptor.instructions_file)
    instructions = instruction_path.read_text(encoding="utf-8").strip()

    input_schema = (
        _read_json_object(
            _safe_file(package_root, descriptor.input_schema_file)
        )
        if descriptor.input_schema_file is not None
        else None
    )
    output_schema = (
        _read_json_object(
            _safe_file(package_root, descriptor.output_schema_file)
        )
        if descriptor.output_schema_file is not None
        else None
    )
    _validate_schema_dialect(input_schema, "input")
    _validate_schema_dialect(output_schema, "output")

    referenced = [
        descriptor.instructions_file,
        *descriptor.summary.resources,
        *descriptor.summary.evals,
    ]
    if descriptor.input_schema_file is not None:
        referenced.append(descriptor.input_schema_file)
    if descriptor.output_schema_file is not None:
        referenced.append(descriptor.output_schema_file)
    for relative in referenced:
        _safe_file(package_root, relative)

    digest = _package_digest(
        package_root,
        data,
        tuple(dict.fromkeys(referenced)),
    )
    return replace(
        descriptor.summary,
        instructions=instructions,
        input_schema=input_schema,
        output_schema=output_schema,
        package_digest=f"sha256:{digest}",
        detail_level="full",
    )


def semantic_version_key(version: str) -> tuple[int, int, int, int, str]:
    match = _SEMVER_RE.fullmatch(version.strip())
    if match is None:
        raise ValueError(f"version must be semantic major.minor.patch: {version}")
    major, minor, patch, prerelease, _build = match.groups()
    # Stable versions sort after prereleases of the same core version.
    stable_rank = 1 if prerelease is None else 0
    return int(major), int(minor), int(patch), stable_rank, prerelease or ""


def _descriptor_from_data(
    manifest_path: Path,
    data: dict[str, Any],
) -> EgoPackageDescriptor:
    schema_version = int(data.get("schema_version", 1))
    if schema_version != EGO_PACKAGE_SCHEMA_VERSION:
        raise ValueError(
            f"{manifest_path}: unsupported E.G.O package schema "
            f"{schema_version}; expected {EGO_PACKAGE_SCHEMA_VERSION}"
        )
    version = _required_string(data, "version", manifest_path)
    semantic_version_key(version)

    risk_raw = data.get("risk", {})
    if not isinstance(risk_raw, dict):
        raise ValueError(f"{manifest_path}: risk must be an object")
    risk = EgoRiskHints(
        read_only=_bool(risk_raw.get("read_only", False), "risk.read_only", manifest_path),
        destructive=_bool(
            risk_raw.get("destructive", True),
            "risk.destructive",
            manifest_path,
        ),
        idempotent=_bool(
            risk_raw.get("idempotent", False),
            "risk.idempotent",
            manifest_path,
        ),
        open_world=_bool(
            risk_raw.get("open_world", True),
            "risk.open_world",
            manifest_path,
        ),
    )

    runtime_raw = data.get("runtime", {"type": "prompt"})
    if isinstance(runtime_raw, str):
        runtime_type = runtime_raw
    elif isinstance(runtime_raw, dict):
        runtime_type = str(runtime_raw.get("type", "prompt")).strip()
    else:
        raise ValueError(f"{manifest_path}: runtime must be string or object")

    instructions_file = str(data.get("instructions_file", "SKILL.md")).strip()
    _validate_relative_path(instructions_file, manifest_path)

    input_schema_file = _optional_path(
        data.get("input_schema_file"),
        manifest_path,
    )
    output_schema_file = _optional_path(
        data.get("output_schema_file"),
        manifest_path,
    )
    resources = tuple(
        _string_list(data.get("resources", []), "resources", manifest_path)
    )
    evals = tuple(
        _string_list(data.get("evals", []), "evals", manifest_path)
    )
    for value in (*resources, *evals):
        _validate_relative_path(value, manifest_path)

    summary = EgoManifest(
        ego_id=_required_string(data, "ego_id", manifest_path),
        name=_required_string(data, "name", manifest_path),
        provides=tuple(
            _string_list(data.get("provides", []), "provides", manifest_path)
        ),
        keywords=tuple(
            _string_list(data.get("keywords", []), "keywords", manifest_path)
        ),
        instructions="",
        permissions=_permissions(data.get("permissions", {}), manifest_path),
        schema_version=schema_version,
        version=version,
        description=_required_string(data, "description", manifest_path),
        tags=tuple(_string_list(data.get("tags", []), "tags", manifest_path)),
        examples=tuple(
            _string_list(data.get("examples", []), "examples", manifest_path)
        ),
        requires=tuple(
            _string_list(data.get("requires", []), "requires", manifest_path)
        ),
        conflicts=tuple(
            _string_list(data.get("conflicts", []), "conflicts", manifest_path)
        ),
        risk=risk,
        runtime_type=runtime_type,
        resources=resources,
        evals=evals,
        detail_level="metadata",
    )
    return EgoPackageDescriptor(
        root=manifest_path.parent,
        manifest_path=manifest_path,
        summary=summary,
        instructions_file=instructions_file,
        input_schema_file=input_schema_file,
        output_schema_file=output_schema_file,
    )


def _read_manifest(path: Path) -> dict[str, Any]:
    data = _read_json_object(path)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: manifest must be an object")
    return data


def _read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path}: JSON root must be an object")
    return value


def _package_digest(
    root: Path,
    manifest: dict[str, Any],
    files: tuple[str, ...],
) -> str:
    digest = sha256()
    canonical = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest.update(b"manifest.json\\0")
    digest.update(canonical)
    for relative in sorted(files):
        path = _safe_file(root, relative)
        digest.update(b"\\0")
        digest.update(relative.replace("\\", "/").encode("utf-8"))
        digest.update(b"\\0")
        digest.update(path.read_bytes())
    return digest.hexdigest()


def _safe_file(root: Path, relative: str | None) -> Path:
    if relative is None:
        raise ValueError("package path cannot be null")
    _validate_relative_path(relative, root / "manifest.json")
    root_resolved = root.resolve()
    path = (root / relative.replace("\\", "/")).resolve()
    if not path.is_relative_to(root_resolved):
        raise ValueError(f"package path escapes root: {relative}")
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def _validate_relative_path(value: str, manifest_path: Path) -> None:
    text = str(value).strip()
    if not text:
        raise ValueError(f"{manifest_path}: package path must be non-empty")
    posix = PurePosixPath(text.replace("\\", "/"))
    windows = PureWindowsPath(text)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"{manifest_path}: package path must be relative: {value}")
    if ".." in posix.parts or ".." in windows.parts:
        raise ValueError(f"{manifest_path}: package path may not escape root: {value}")


def _validate_schema_dialect(
    schema: dict[str, Any] | None,
    label: str,
) -> None:
    if schema is None:
        return
    dialect = schema.get("$schema")
    if dialect is not None and dialect != JSON_SCHEMA_2020_12:
        raise ValueError(
            f"{label} schema dialect must be JSON Schema 2020-12"
        )


def _required_string(data: dict[str, Any], key: str, path: Path) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: {key} must be a non-empty string")
    return value.strip()


def _string_list(value: Any, key: str, path: Path) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) for item in value
    ):
        raise ValueError(f"{path}: {key} must be a list of strings")
    return [item.strip() for item in value if item.strip()]


def _permissions(value: Any, path: Path) -> dict[str, str | bool]:
    if not isinstance(value, dict):
        raise ValueError(f"{path}: permissions must be an object")
    result: dict[str, str | bool] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, (str, bool)):
            raise ValueError(
                f"{path}: permissions values must be string or boolean"
            )
        result[key] = item
    return result


def _bool(value: Any, key: str, path: Path) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{path}: {key} must be boolean")
    return value


def _optional_path(value: Any, path: Path) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{path}: schema file path must be a non-empty string")
    result = value.strip()
    _validate_relative_path(result, path)
    return result
