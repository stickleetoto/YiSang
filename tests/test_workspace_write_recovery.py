from __future__ import annotations

from hashlib import sha256

import pytest

from yisang.execution import ToolRegistry, register_workspace_write_tools


def _hash(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def test_workspace_write_text_is_atomic_and_reports_hash(tmp_path):
    registry = ToolRegistry()
    register_workspace_write_tools(registry, root=tmp_path)
    tool = registry.get("workspace.write_text")

    result = tool.handler(
        {
            "path": "docs/state.txt",
            "content": "hello",
            "create_parents": True,
        }
    )

    assert (tmp_path / "docs" / "state.txt").read_text(encoding="utf-8") == "hello"
    assert result["sha256"] == _hash("hello")
    assert result["previous_sha256"] is None
    assert result["changed"] is True


def test_workspace_write_text_enforces_precondition(tmp_path):
    target = tmp_path / "state.txt"
    target.write_text("old", encoding="utf-8")
    registry = ToolRegistry()
    register_workspace_write_tools(registry, root=tmp_path)
    tool = registry.get("workspace.write_text")

    with pytest.raises(ValueError, match="precondition failed"):
        tool.handler(
            {
                "path": "state.txt",
                "content": "new",
                "expected_sha256": _hash("different"),
            }
        )

    assert target.read_text(encoding="utf-8") == "old"


def test_workspace_write_text_blocks_escape(tmp_path):
    registry = ToolRegistry()
    register_workspace_write_tools(registry, root=tmp_path)
    tool = registry.get("workspace.write_text")

    with pytest.raises(PermissionError, match="escapes workspace"):
        tool.handler({"path": "../escape.txt", "content": "nope"})


def test_workspace_write_recovery_metadata_contains_no_content(tmp_path):
    registry = ToolRegistry()
    register_workspace_write_tools(registry, root=tmp_path)
    tool = registry.get("workspace.write_text")

    metadata = tool.build_recovery_metadata(
        {"path": "a.txt", "content": "secret-content"}
    )

    assert metadata["workspace_path"] == "a.txt"
    assert metadata["expected_sha256"] == _hash("secret-content")
    assert "secret-content" not in repr(metadata)
