from __future__ import annotations

from pathlib import Path
from typing import Any

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
