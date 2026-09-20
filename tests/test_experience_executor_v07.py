from __future__ import annotations

import sys

import pytest

from yisang.experience import (
    DeterministicReplayExecutor,
    ExperienceEvidence,
    ExperienceEpisode,
    ExperienceGeneralizer,
    FileExpectation,
    ReplayExecutionError,
    ReplayExecutionSpec,
    ReplayPlanBuilder,
    ReplaySetupFile,
)


def _plan():
    episodes = tuple(
        ExperienceEpisode(
            episode_id=f"episode-{index}",
            outcome="success",
            summary="verified",
            evidence=(
                ExperienceEvidence(
                    evidence_ref=f"test:{index}",
                    source_type="test_result",
                    summary="verified",
                    verified=True,
                ),
            ),
            trigger_conditions=("replay",),
            procedure_steps=("tool:python",),
        )
        for index in range(3)
    )
    candidate = ExperienceGeneralizer().generalize(episodes)
    return candidate, ReplayPlanBuilder().build(candidate, episodes)


def _executor(tmp_path):
    return DeterministicReplayExecutor(
        allowed_executables=(sys.executable,),
        workspace_root=tmp_path,
        max_timeout_seconds=2.0,
    )


def test_executor_runs_command_and_checks_exact_file(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=(
                sys.executable,
                "-c",
                "from pathlib import Path; Path('x.txt').write_text('OK'); print('done')",
            ),
            stdout_contains=("done",),
            file_expectations=(FileExpectation("x.txt", exact_text="OK"),),
        )
        for case in plan.cases
    )

    report = _executor(tmp_path).execute(plan, specs)

    assert all(result.passed for result in report.results)
    assert all(
        result.evidence_refs[0].startswith("replay-exec-sha256:")
        for result in report.results
    )


def test_executor_reports_exit_code_failure(tmp_path) -> None:
    _, plan = _plan()
    specs = []
    for index, case in enumerate(plan.cases):
        code = 7 if index == 0 else 0
        specs.append(
            ReplayExecutionSpec(
                test_id=case.test_id,
                argv=(sys.executable, "-c", f"raise SystemExit({code})"),
            )
        )

    report = _executor(tmp_path).execute(plan, specs)

    assert report.results[0].passed is False
    assert "exit_code==0" in report.results[0].detail
    assert all(result.passed for result in report.results[1:])


def test_executor_reports_stdout_failure(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=(sys.executable, "-c", "print('actual')"),
            stdout_contains=("expected",),
        )
        for case in plan.cases
    )

    report = _executor(tmp_path).execute(plan, specs)

    assert all(not result.passed for result in report.results)
    assert "stdout_contains:expected" in report.results[0].detail


def test_executor_reports_file_exact_failure(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=(
                sys.executable,
                "-c",
                "from pathlib import Path; Path('x.txt').write_text('WRONG')",
            ),
            file_expectations=(FileExpectation("x.txt", exact_text="RIGHT"),),
        )
        for case in plan.cases
    )

    report = _executor(tmp_path).execute(plan, specs)

    assert all(not result.passed for result in report.results)
    assert "file_exact:x.txt" in report.results[0].detail


def test_executor_writes_setup_files_inside_workspace(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=(
                sys.executable,
                "-c",
                "from pathlib import Path; print(Path('input.txt').read_text())",
            ),
            setup_files=(ReplaySetupFile("input.txt", "INPUT_OK"),),
            stdout_contains=("INPUT_OK",),
        )
        for case in plan.cases
    )

    report = _executor(tmp_path).execute(plan, specs)
    assert all(result.passed for result in report.results)


def test_rejects_workspace_path_traversal() -> None:
    with pytest.raises(ValueError, match="escape workspace"):
        ReplayExecutionSpec(
            test_id="x",
            argv=(sys.executable, "-c", "pass"),
            setup_files=(ReplaySetupFile("../escape.txt", "bad"),),
        )


def test_rejects_unapproved_executable(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=("definitely-not-approved",),
        )
        for case in plan.cases
    )

    with pytest.raises(ReplayExecutionError, match="not allowed"):
        _executor(tmp_path).execute(plan, specs)


def test_rejects_missing_execution_spec(tmp_path) -> None:
    _, plan = _plan()
    only_one = ReplayExecutionSpec(
        test_id=plan.cases[0].test_id,
        argv=(sys.executable, "-c", "pass"),
    )
    with pytest.raises(ReplayExecutionError, match="missing replay execution specs"):
        _executor(tmp_path).execute(plan, (only_one,))


def test_timeout_becomes_failed_replay_result(tmp_path) -> None:
    _, plan = _plan()
    specs = tuple(
        ReplayExecutionSpec(
            test_id=case.test_id,
            argv=(sys.executable, "-c", "import time; time.sleep(0.2)"),
            timeout_seconds=0.05,
        )
        for case in plan.cases
    )

    report = _executor(tmp_path).execute(plan, specs)
    assert all(not result.passed for result in report.results)
    assert all("timeout" in result.detail for result in report.results)
