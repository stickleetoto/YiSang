from __future__ import annotations

import json
from pathlib import Path

from yisang.gym.models import GymTaskSpec
from yisang.gym.runner import check_run, prepare_run


def _write_task(root: Path, *, allowed_paths=None, max_changed_files=1) -> Path:
    task_dir = root / "task"
    seed = task_dir / "seed"
    seed.mkdir(parents=True)
    (seed / "solution.txt").write_text("todo", encoding="utf-8")

    spec = {
        "id": "test-task",
        "title": "Test task",
        "difficulty": "easy",
        "goal": "Change solution.txt to exactly ok.",
        "allowed_paths": allowed_paths or ["solution.txt"],
        "required_paths": ["solution.txt"],
        "max_changed_files": max_changed_files,
        "forbidden_actions": ["No network access"],
        "verify": [
            [
                "{python}",
                "-c",
                (
                    "from pathlib import Path; "
                    "assert Path('solution.txt').read_text(encoding='utf-8') == 'ok'"
                ),
            ]
        ],
    }
    (task_dir / "task.json").write_text(
        json.dumps(spec, indent=2),
        encoding="utf-8",
    )
    return task_dir


def test_task_spec_loads_valid_definition(tmp_path):
    task_dir = _write_task(tmp_path)

    spec = GymTaskSpec.from_file(task_dir / "task.json")

    assert spec.task_id == "test-task"
    assert spec.allowed_paths == ("solution.txt",)
    assert spec.max_changed_files == 1
    assert spec.verify[0][0] == "{python}"


def test_prepare_then_check_requires_verification_success(tmp_path):
    task_dir = _write_task(tmp_path)
    run = prepare_run(task_dir, runs_root=tmp_path / "runs")

    first = check_run(run.run_dir)
    assert first.scope_ok is True
    assert first.verification_ok is False
    assert first.ready is False

    (run.workspace / "solution.txt").write_text("ok", encoding="utf-8")
    second = check_run(run.run_dir)

    assert second.ready is True
    assert second.scope_ok is True
    assert second.verification_ok is True
    assert second.changed_files == ("solution.txt",)
    assert second.violations == ()
    assert (run.run_dir / "result.json").is_file()


def test_check_rejects_change_outside_allowlist(tmp_path):
    task_dir = _write_task(tmp_path)
    run = prepare_run(task_dir, runs_root=tmp_path / "runs")
    (run.workspace / "solution.txt").write_text("ok", encoding="utf-8")
    (run.workspace / "extra.txt").write_text("unexpected", encoding="utf-8")

    result = check_run(run.run_dir)

    assert result.verification_ok is True
    assert result.scope_ok is False
    assert result.ready is False
    assert "extra.txt" in result.changed_files
    assert any(
        "path outside allowlist changed: extra.txt" == item
        for item in result.violations
    )


def test_check_rejects_protected_task_brief_change(tmp_path):
    task_dir = _write_task(tmp_path)
    run = prepare_run(task_dir, runs_root=tmp_path / "runs")
    (run.workspace / "solution.txt").write_text("ok", encoding="utf-8")
    (run.workspace / "GYM_TASK.md").write_text("tampered", encoding="utf-8")

    result = check_run(run.run_dir)

    assert result.ready is False
    assert any(
        item == "protected path changed: GYM_TASK.md"
        for item in result.violations
    )


def test_check_enforces_max_changed_files(tmp_path):
    task_dir = _write_task(
        tmp_path,
        allowed_paths=["*.txt"],
        max_changed_files=1,
    )
    run = prepare_run(task_dir, runs_root=tmp_path / "runs")
    (run.workspace / "solution.txt").write_text("ok", encoding="utf-8")
    (run.workspace / "notes.txt").write_text("extra", encoding="utf-8")

    result = check_run(run.run_dir)

    assert result.verification_ok is True
    assert result.scope_ok is False
    assert any("changed file count 2 exceeds limit 1" == item for item in result.violations)


def test_prepare_keeps_manifest_outside_agent_workspace(tmp_path):
    task_dir = _write_task(tmp_path)
    run = prepare_run(task_dir, runs_root=tmp_path / "runs")

    assert (run.run_dir / "manifest.json").is_file()
    assert not (run.workspace / "manifest.json").exists()
    assert (run.workspace / "GYM_TASK.md").is_file()
