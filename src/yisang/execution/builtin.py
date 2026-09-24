from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
from typing import Any
import uuid

from .tools import ToolDefinition, ToolRegistry


def register_workspace_read_tools(
    registry: ToolRegistry,
    *,
    root: str | Path,
    max_file_bytes: int = 256_000,
    max_entries: int = 200,
) -> None:
    if max_file_bytes <= 0 or max_entries <= 0:
        raise ValueError("workspace limits must be positive")

    workspace = Path(root).resolve()

    def list_dir(arguments: dict[str, Any]) -> list[dict[str, str]]:
        target = _resolve_under(workspace, arguments.get("path", "."))
        if not target.is_dir():
            raise NotADirectoryError(str(arguments.get("path", ".")))

        items = []
        for child in sorted(target.iterdir(), key=lambda p: p.name.lower())[:max_entries]:
            resolved = child.resolve()
            if not _is_under(workspace, resolved):
                continue
            items.append(
                {
                    "path": resolved.relative_to(workspace).as_posix(),
                    "kind": "dir" if resolved.is_dir() else "file",
                }
            )
        return items

    def read_text(arguments: dict[str, Any]) -> str:
        raw_path = arguments.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise ValueError("path must be a non-empty string")

        target = _resolve_under(workspace, raw_path)
        if not target.is_file():
            raise FileNotFoundError(raw_path)

        size = target.stat().st_size
        if size > max_file_bytes:
            raise ValueError(
                f"file exceeds max_file_bytes ({size} > {max_file_bytes})"
            )
        return target.read_text(encoding="utf-8")

    registry.register(
        ToolDefinition(
            tool_id="workspace.list",
            handler=list_dir,
            description="List files and directories inside the configured workspace.",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative directory path. Defaults to '.'.",
                    }
                },
                "additionalProperties": False,
            },
        )
    )
    registry.register(
        ToolDefinition(
            tool_id="workspace.read_text",
            handler=read_text,
            description="Read a UTF-8 text file inside the configured workspace.",
            required_capabilities=("repository_analysis",),
            required_permissions={"filesystem": "read"},
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Workspace-relative file path.",
                    }
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        )
    )


def _resolve_under(root: Path, raw: Any) -> Path:
    if not isinstance(raw, str):
        raise ValueError("path must be a string")
    candidate = (root / raw).resolve()
    if not _is_under(root, candidate):
        raise PermissionError("path escapes workspace")
    return candidate


def _is_under(root: Path, candidate: Path) -> bool:
    return candidate == root or root in candidate.parents



def register_workspace_write_tools(
    registry: ToolRegistry,
    *,
    root: str | Path,
    max_file_bytes: int = 256_000,
) -> None:
    """Register recovery-aware workspace-local UTF-8 write capability."""

    if max_file_bytes <= 0:
        raise ValueError("max_file_bytes must be positive")

    workspace = Path(root).resolve()

    def recovery_metadata(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_path = _required_text(arguments.get("path"), "path")
        content = _required_content(arguments.get("content"))
        target = _resolve_under(workspace, raw_path)
        encoded = content.encode("utf-8")
        if len(encoded) > max_file_bytes:
            raise ValueError(
                f"content exceeds max_file_bytes ({len(encoded)} > {max_file_bytes})"
            )
        return {
            "recovery_kind": "workspace.write_text",
            "workspace_path": target.relative_to(workspace).as_posix(),
            "expected_sha256": _sha256_bytes(encoded),
            "expected_bytes": len(encoded),
        }

    def write_text(arguments: dict[str, Any]) -> dict[str, Any]:
        raw_path = _required_text(arguments.get("path"), "path")
        content = _required_content(arguments.get("content"))
        create_parents = arguments.get("create_parents", False)
        must_not_exist = arguments.get("must_not_exist", False)
        expected_sha256 = arguments.get("expected_sha256")

        if not isinstance(create_parents, bool):
            raise ValueError("create_parents must be boolean")
        if not isinstance(must_not_exist, bool):
            raise ValueError("must_not_exist must be boolean")
        if expected_sha256 is not None and not isinstance(expected_sha256, str):
            raise ValueError("expected_sha256 must be a string")

        target = _resolve_under(workspace, raw_path)
        if target.exists() and target.is_dir():
            raise IsADirectoryError(raw_path)

        encoded = content.encode("utf-8")
        if len(encoded) > max_file_bytes:
            raise ValueError(
                f"content exceeds max_file_bytes ({len(encoded)} > {max_file_bytes})"
            )

        parent = target.parent
        if not parent.exists():
            if not create_parents:
                raise FileNotFoundError(
                    f"parent directory does not exist: "
                    f"{parent.relative_to(workspace).as_posix()}"
                )
            parent.mkdir(parents=True, exist_ok=True)
            resolved_parent = parent.resolve()
            if not _is_under(workspace, resolved_parent):
                raise PermissionError("parent path escapes workspace")

        previous_sha256 = None
        if target.exists():
            previous_sha256 = _sha256_bytes(target.read_bytes())

        if must_not_exist and target.exists():
            raise FileExistsError(raw_path)

        if expected_sha256 is not None:
            normalized_expected = _normalize_sha256(expected_sha256)
            if previous_sha256 != normalized_expected:
                raise ValueError(
                    "workspace write precondition failed: "
                    f"expected {normalized_expected}, got {previous_sha256}"
                )

        expected_new_sha256 = _sha256_bytes(encoded)
        temp = parent / (
            f".{target.name}.yisang-{uuid.uuid4().hex[:12]}.tmp"
        )
        try:
            with temp.open("wb") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, target)
        finally:
            if temp.exists():
                temp.unlink()

        return {
            "path": target.relative_to(workspace).as_posix(),
            "bytes": len(encoded),
            "sha256": expected_new_sha256,
            "previous_sha256": previous_sha256,
            "changed": previous_sha256 != expected_new_sha256,
        }

    registry.register(
        ToolDefinition(
            tool_id="workspace.write_text",
            handler=write_text,
            description=(
                "Atomically write a UTF-8 text file inside the configured "
                "workspace."
            ),
            required_capabilities=("repository_edit",),
            required_permissions={"filesystem": "workspace"},
            argument_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "create_parents": {"type": "boolean"},
                    "must_not_exist": {"type": "boolean"},
                    "expected_sha256": {"type": "string"},
                },
                "required": ["path", "content"],
                "additionalProperties": False,
            },
            side_effecting=True,
            policy_action="filesystem.write",
            resource_type="workspace_path",
            resource_argument="path",
            recovery_metadata_builder=recovery_metadata,
        )
    )


def _required_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    return value


def _required_content(value: Any) -> str:
    if not isinstance(value, str):
        raise ValueError("content must be a string")
    return value


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + sha256(value).hexdigest()


def _normalize_sha256(value: str) -> str:
    normalized = value.strip().lower()
    if normalized.startswith("sha256:"):
        digest = normalized[7:]
    else:
        digest = normalized
    if len(digest) != 64 or any(
        char not in "0123456789abcdef" for char in digest
    ):
        raise ValueError("expected_sha256 must be a SHA-256 digest")
    return "sha256:" + digest
