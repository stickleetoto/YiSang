from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import subprocess
from tempfile import TemporaryDirectory
from typing import Iterable

from .models import ReplayCaseResult, ReplayReport
from .replay import ReplayPlan


class ReplayExecutionError(ValueError):
    pass


@dataclass(frozen=True)
class ReplaySetupFile:
    path: str
    content: str


@dataclass(frozen=True)
class FileExpectation:
    path: str
    must_exist: bool = True
    exact_text: str | None = None


@dataclass(frozen=True)
class ReplayExecutionSpec:
    test_id: str
    argv: tuple[str, ...]
    expected_exit_code: int = 0
    stdout_contains: tuple[str, ...] = ()
    stderr_contains: tuple[str, ...] = ()
    setup_files: tuple[ReplaySetupFile, ...] = ()
    file_expectations: tuple[FileExpectation, ...] = ()
    timeout_seconds: float = 30.0

    def __post_init__(self) -> None:
        if not self.test_id.strip():
            raise ValueError("test_id must be non-empty")
        if not self.argv or not str(self.argv[0]).strip():
            raise ValueError("argv must contain an executable")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        for item in self.setup_files:
            _validate_relative_path(item.path)
        for item in self.file_expectations:
            _validate_relative_path(item.path)


class DeterministicReplayExecutor:
    """Execute explicit replay manifests with deterministic local checks.

    This executor never invokes a shell. The caller must explicitly allow every
    executable that a replay manifest may start.
    """

    def __init__(
        self,
        *,
        allowed_executables: Iterable[str],
        workspace_root: str | Path | None = None,
        max_timeout_seconds: float = 60.0,
    ) -> None:
        allowed = tuple(str(item).strip() for item in allowed_executables if str(item).strip())
        if not allowed:
            raise ValueError("allowed_executables must be non-empty")
        if max_timeout_seconds <= 0:
            raise ValueError("max_timeout_seconds must be positive")
        self.allowed_executables = allowed
        self.workspace_root = Path(workspace_root) if workspace_root is not None else None
        self.max_timeout_seconds = max_timeout_seconds

    def execute(
        self,
        plan: ReplayPlan,
        specs: Iterable[ReplayExecutionSpec],
    ) -> ReplayReport:
        by_id: dict[str, ReplayExecutionSpec] = {}
        for spec in specs:
            if spec.test_id in by_id:
                raise ReplayExecutionError(
                    f"duplicate replay execution spec: {spec.test_id}"
                )
            by_id[spec.test_id] = spec

        expected_ids = tuple(case.test_id for case in plan.cases)
        missing = tuple(test_id for test_id in expected_ids if test_id not in by_id)
        extra = tuple(sorted(set(by_id) - set(expected_ids)))
        if missing:
            raise ReplayExecutionError(
                f"missing replay execution specs: {', '.join(missing)}"
            )
        if extra:
            raise ReplayExecutionError(
                f"unexpected replay execution specs: {', '.join(extra)}"
            )

        if self.workspace_root is not None:
            self.workspace_root.mkdir(parents=True, exist_ok=True)

        results = tuple(
            self._execute_case(case.test_id, by_id[case.test_id])
            for case in plan.cases
        )
        return ReplayReport(candidate_id=plan.candidate_id, results=results)

    def _execute_case(
        self,
        test_id: str,
        spec: ReplayExecutionSpec,
    ) -> ReplayCaseResult:
        self._validate_executable(spec.argv[0])
        timeout = min(spec.timeout_seconds, self.max_timeout_seconds)

        with TemporaryDirectory(
            prefix="yisang-replay-",
            dir=str(self.workspace_root) if self.workspace_root is not None else None,
        ) as temp_dir:
            workspace = Path(temp_dir)
            for setup in spec.setup_files:
                path = _workspace_path(workspace, setup.path)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(setup.content, encoding="utf-8")

            try:
                completed = subprocess.run(
                    list(spec.argv),
                    cwd=workspace,
                    capture_output=True,
                    text=True,
                    shell=False,
                    timeout=timeout,
                    check=False,
                    env=os.environ.copy(),
                )
            except subprocess.TimeoutExpired as exc:
                observation = {
                    "test_id": test_id,
                    "status": "timeout",
                    "timeout_seconds": timeout,
                }
                return ReplayCaseResult(
                    test_id=test_id,
                    passed=False,
                    evidence_refs=(_evidence_ref(observation),),
                    detail=f"timeout after {timeout:g}s",
                )
            except OSError as exc:
                observation = {
                    "test_id": test_id,
                    "status": "os_error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                return ReplayCaseResult(
                    test_id=test_id,
                    passed=False,
                    evidence_refs=(_evidence_ref(observation),),
                    detail=f"{type(exc).__name__}: {exc}",
                )

            checks: list[tuple[str, bool]] = [
                (
                    f"exit_code=={spec.expected_exit_code}",
                    completed.returncode == spec.expected_exit_code,
                )
            ]
            checks.extend(
                (f"stdout_contains:{value}", value in completed.stdout)
                for value in spec.stdout_contains
            )
            checks.extend(
                (f"stderr_contains:{value}", value in completed.stderr)
                for value in spec.stderr_contains
            )

            file_observations: list[dict[str, object]] = []
            for expectation in spec.file_expectations:
                path = _workspace_path(workspace, expectation.path)
                exists = path.is_file()
                file_check = exists if expectation.must_exist else not exists
                checks.append((f"file_exists:{expectation.path}", file_check))

                text_sha256: str | None = None
                exact_match: bool | None = None
                if exists:
                    raw = path.read_bytes()
                    text_sha256 = sha256(raw).hexdigest()
                    if expectation.exact_text is not None:
                        actual_text = raw.decode("utf-8")
                        exact_match = actual_text == expectation.exact_text
                        checks.append(
                            (
                                f"file_exact:{expectation.path}",
                                exact_match,
                            )
                        )
                elif expectation.exact_text is not None:
                    exact_match = False
                    checks.append((f"file_exact:{expectation.path}", False))

                file_observations.append(
                    {
                        "path": expectation.path,
                        "exists": exists,
                        "sha256": text_sha256,
                        "exact_match": exact_match,
                    }
                )

            passed = all(ok for _, ok in checks)
            failed_checks = [name for name, ok in checks if not ok]
            observation = {
                "test_id": test_id,
                "status": "completed",
                "returncode": completed.returncode,
                "stdout_sha256": sha256(
                    completed.stdout.encode("utf-8")
                ).hexdigest(),
                "stderr_sha256": sha256(
                    completed.stderr.encode("utf-8")
                ).hexdigest(),
                "file_observations": file_observations,
                "checks": [{"name": name, "passed": ok} for name, ok in checks],
            }
            detail = (
                "deterministic replay passed"
                if passed
                else "failed checks: " + ", ".join(failed_checks)
            )
            return ReplayCaseResult(
                test_id=test_id,
                passed=passed,
                evidence_refs=(_evidence_ref(observation),),
                detail=detail,
            )

    def _validate_executable(self, executable: str) -> None:
        actual = _executable_keys(executable)
        for allowed in self.allowed_executables:
            if actual & _executable_keys(allowed):
                return
        raise ReplayExecutionError(
            f"executable is not allowed for replay: {executable}"
        )


def _validate_relative_path(value: str) -> None:
    text = str(value).strip()
    if not text:
        raise ValueError("replay path must be non-empty")
    posix = PurePosixPath(text.replace("\\", "/"))
    windows = PureWindowsPath(text)
    if posix.is_absolute() or windows.is_absolute() or windows.drive:
        raise ValueError(f"replay path must be relative: {value}")
    if ".." in posix.parts or ".." in windows.parts:
        raise ValueError(f"replay path may not escape workspace: {value}")


def _workspace_path(workspace: Path, value: str) -> Path:
    _validate_relative_path(value)
    path = (workspace / value.replace("\\", "/")).resolve()
    root = workspace.resolve()
    if not path.is_relative_to(root):
        raise ReplayExecutionError(
            f"replay path escaped workspace: {value}"
        )
    return path


def _executable_keys(value: str) -> set[str]:
    text = str(value).strip()
    keys = {os.path.normcase(text)}
    keys.add(os.path.normcase(Path(text).name))
    try:
        keys.add(os.path.normcase(str(Path(text).resolve())))
    except OSError:
        pass
    return keys


def _evidence_ref(observation: dict[str, object]) -> str:
    payload = json.dumps(
        observation,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"replay-exec-sha256:{digest}"
