from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from fnmatch import fnmatchcase
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any
from uuid import uuid4

from .models import GymTaskSpec


_MANIFEST_NAME = "manifest.json"
_RESULT_NAME = "result.json"
_WORKSPACE_NAME = "workspace"
_TASK_BRIEF_NAME = "GYM_TASK.md"

_IGNORED_PATTERNS = (
    "__pycache__/**",
    "**/__pycache__/**",
    ".pytest_cache/**",
    "**/.pytest_cache/**",
    ".coverage",
    "coverage.xml",
)


@dataclass(frozen=True)
class GymRun:
    run_dir: Path
    workspace: Path
    task: GymTaskSpec


@dataclass(frozen=True)
class GymCheckResult:
    task_id: str
    ready: bool
    scope_ok: bool
    verification_ok: bool
    changed_files: tuple[str, ...]
    violations: tuple[str, ...]
    commands: tuple[dict[str, Any], ...]
    duration_seconds: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "ready": self.ready,
            "scope_ok": self.scope_ok,
            "verification_ok": self.verification_ok,
            "changed_files": list(self.changed_files),
            "violations": list(self.violations),
            "commands": list(self.commands),
            "duration_seconds": round(self.duration_seconds, 6),
        }


def prepare_run(
    task_dir: str | Path,
    *,
    runs_root: str | Path = ".gym/runs",
) -> GymRun:
    task_path = Path(task_dir).resolve()
    spec_path = task_path / "task.json"
    seed_path = task_path / "seed"
    if not spec_path.is_file():
        raise ValueError(f"missing task spec: {spec_path}")
    if not seed_path.is_dir():
        raise ValueError(f"missing seed directory: {seed_path}")

    task = GymTaskSpec.from_file(spec_path)
    run_id = (
        f"{task.task_id}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}-"
        f"{uuid4().hex[:8]}"
    )
    run_dir = Path(runs_root).resolve() / run_id
    workspace = run_dir / _WORKSPACE_NAME
    run_dir.mkdir(parents=True, exist_ok=False)
    shutil.copytree(seed_path, workspace)

    _assert_no_symlinks(workspace)
    brief = workspace / _TASK_BRIEF_NAME
    brief.write_text(_render_task_brief(task), encoding="utf-8")

    baseline = _snapshot(workspace)
    manifest = {
        "schema_version": 1,
        "task": task.to_dict(),
        "task_source": str(task_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
        "workspace": _WORKSPACE_NAME,
        "baseline": baseline,
        "protected_paths": [_TASK_BRIEF_NAME],
    }
    (run_dir / _MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return GymRun(run_dir=run_dir, workspace=workspace, task=task)


def check_run(run_dir: str | Path) -> GymCheckResult:
    started = time.monotonic()
    root = Path(run_dir).resolve()
    manifest_path = root / _MANIFEST_NAME
    if not manifest_path.is_file():
        raise ValueError(f"missing gym manifest: {manifest_path}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("unsupported or invalid gym manifest")

    task_raw = manifest.get("task")
    if not isinstance(task_raw, dict):
        raise ValueError("manifest task is invalid")
    task = _task_from_manifest(task_raw)

    workspace_name = manifest.get("workspace")
    if workspace_name != _WORKSPACE_NAME:
        raise ValueError("manifest workspace is invalid")
    workspace = root / _WORKSPACE_NAME
    if not workspace.is_dir():
        raise ValueError(f"missing workspace: {workspace}")

    baseline = manifest.get("baseline")
    if not isinstance(baseline, dict):
        raise ValueError("manifest baseline is invalid")
    if any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in baseline.items()
    ):
        raise ValueError("manifest baseline entries are invalid")

    protected = manifest.get("protected_paths", [])
    if not isinstance(protected, list) or any(
        not isinstance(item, str) for item in protected
    ):
        raise ValueError("manifest protected_paths are invalid")

    violations: list[str] = []
    try:
        _assert_no_symlinks(workspace)
    except ValueError as exc:
        violations.append(str(exc))

    current = _snapshot(workspace, reject_symlinks=False)
    changed = sorted(
        path
        for path in set(baseline) | set(current)
        if baseline.get(path) != current.get(path)
        and not _matches_any(path, _IGNORED_PATTERNS)
    )

    for path in changed:
        if path in protected:
            violations.append(f"protected path changed: {path}")
            continue
        if not _matches_any(path, task.allowed_paths):
            violations.append(f"path outside allowlist changed: {path}")

    if task.max_changed_files is not None and len(changed) > task.max_changed_files:
        violations.append(
            f"changed file count {len(changed)} exceeds limit "
            f"{task.max_changed_files}"
        )

    for required in task.required_paths:
        candidate = workspace / Path(required)
        if not candidate.is_file():
            violations.append(f"required file missing: {required}")

    command_results: list[dict[str, Any]] = []
    verification_ok = False
    if not any("symlink" in item.lower() for item in violations):
        verification_ok = True
        for command in task.verify:
            argv = [_expand_arg(part) for part in command]
            completed = subprocess.run(
                argv,
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
                env=_verification_env(),
            )
            record = {
                "argv": argv,
                "returncode": completed.returncode,
                "stdout": completed.stdout[-12000:],
                "stderr": completed.stderr[-12000:],
            }
            command_results.append(record)
            if completed.returncode != 0:
                verification_ok = False
                break

    scope_ok = not violations
    result = GymCheckResult(
        task_id=task.task_id,
        ready=scope_ok and verification_ok,
        scope_ok=scope_ok,
        verification_ok=verification_ok,
        changed_files=tuple(changed),
        violations=tuple(violations),
        commands=tuple(command_results),
        duration_seconds=time.monotonic() - started,
    )
    (root / _RESULT_NAME).write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return result


def _task_from_manifest(raw: dict[str, Any]) -> GymTaskSpec:
    text_fields = [raw.get("id"), raw.get("title"), raw.get("difficulty"), raw.get("goal")]
    if any(not isinstance(value, str) or not value.strip() for value in text_fields):
        raise ValueError("manifest task text fields are invalid")

    allowed = raw.get("allowed_paths")
    required = raw.get("required_paths", [])
    forbidden = raw.get("forbidden_actions", [])
    verify = raw.get("verify")
    if not isinstance(allowed, list) or any(
        not isinstance(item, str) or not item for item in allowed
    ):
        raise ValueError("manifest allowed_paths are invalid")
    if not isinstance(required, list) or any(
        not isinstance(item, str) or not item for item in required
    ):
        raise ValueError("manifest required_paths are invalid")
    if not isinstance(forbidden, list) or any(
        not isinstance(item, str) or not item for item in forbidden
    ):
        raise ValueError("manifest forbidden_actions are invalid")
    if not isinstance(verify, list) or not verify:
        raise ValueError("manifest verify is invalid")

    commands: list[tuple[str, ...]] = []
    for command in verify:
        if (
            not isinstance(command, list)
            or not command
            or any(not isinstance(part, str) or not part for part in command)
        ):
            raise ValueError("manifest verify command is invalid")
        commands.append(tuple(command))

    max_changed = raw.get("max_changed_files")
    if max_changed is not None and (
        not isinstance(max_changed, int) or max_changed <= 0
    ):
        raise ValueError("manifest max_changed_files is invalid")

    return GymTaskSpec(
        task_id=text_fields[0].strip(),
        title=text_fields[1].strip(),
        difficulty=text_fields[2].strip(),
        goal=text_fields[3].strip(),
        allowed_paths=tuple(allowed),
        required_paths=tuple(required),
        verify=tuple(commands),
        forbidden_actions=tuple(forbidden),
        max_changed_files=max_changed,
    )


def _snapshot(root: Path, *, reject_symlinks: bool = True) -> dict[str, str]:
    if reject_symlinks:
        _assert_no_symlinks(root)
    result: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            continue
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def _assert_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            relative = path.relative_to(root).as_posix()
            raise ValueError(
                f"symlink is not allowed in gym workspace: {relative}"
            )


def _matches_any(path: str, patterns: tuple[str, ...] | list[str]) -> bool:
    return any(
        fnmatchcase(path, pattern) or Path(path).match(pattern)
        for pattern in patterns
    )


def _expand_arg(value: str) -> str:
    if value == "{python}":
        return sys.executable
    return value


def _verification_env() -> dict[str, str]:
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.setdefault("PYTHONUTF8", "1")
    return env


def _render_task_brief(task: GymTaskSpec) -> str:
    lines = [
        f"# YiSang Gym Task {task.task_id}",
        "",
        f"**{task.title}** — difficulty: {task.difficulty}",
        "",
        task.goal,
        "",
        "## Safety boundary",
        "",
        "Work only inside this workspace. Do not modify the parent run directory.",
        "Only the following paths may be changed:",
    ]
    lines.extend(f"- {pattern}" for pattern in task.allowed_paths)
    if task.max_changed_files is not None:
        lines.append(f"- Maximum changed files: {task.max_changed_files}")
    if task.forbidden_actions:
        lines.extend(["", "Forbidden actions:"])
        lines.extend(f"- {item}" for item in task.forbidden_actions)
    lines.extend(
        [
            "",
            "Do not edit this GYM_TASK.md file.",
            "Finish only after the task tests pass.",
            "",
        ]
    )
    return "\n".join(lines)
