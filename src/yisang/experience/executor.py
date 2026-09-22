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

    def __post_init__(self) -> None:
        _validate_relative_path(self.path)
        if not self.must_exist and self.exact_text is not None:
            raise ValueError("exact_text requires must_exist=True")


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
        if self.workspace_root is not None:
            self.workspace_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(
            prefix="yisang-replay-",
            dir=str(self.workspace_root) if self.workspace_root is not None else None,
        ) as temp_dir:
            return self._execute_case_in_workspace(
                test_id,
                spec,
                Path(temp_dir),
            )

    def _execute_case_in_workspace(
        self,
        test_id: str,
        spec: ReplayExecutionSpec,
        workspace: Path,
    ) -> ReplayCaseResult:
        self._validate_executable(spec.argv[0])
        timeout = min(spec.timeout_seconds, self.max_timeout_seconds)

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
        except subprocess.TimeoutExpired:
            observation = {
                "test_id": test_id,
                "status": "timeout",
                "timeout_seconds": timeout,
                "manifest_sha256": _manifest_digest(spec),
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
                "manifest_sha256": _manifest_digest(spec),
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
            "manifest_sha256": _manifest_digest(spec),
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
        actual_text = str(executable).strip()
        actual_path = Path(actual_text)
        actual_has_path = (
            actual_path.is_absolute()
            or "/" in actual_text
            or "\\" in actual_text
        )
        for allowed in self.allowed_executables:
            allowed_text = str(allowed).strip()
            allowed_path = Path(allowed_text)
            allowed_has_path = (
                allowed_path.is_absolute()
                or "/" in allowed_text
                or "\\" in allowed_text
            )
            if allowed_has_path:
                if not actual_has_path:
                    continue
                if os.path.normcase(str(actual_path.resolve())) == os.path.normcase(
                    str(allowed_path.resolve())
                ):
                    return
            elif os.path.normcase(actual_path.name) == os.path.normcase(
                allowed_path.name
            ):
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


def _manifest_digest(spec: ReplayExecutionSpec) -> str:
    payload = {
        "test_id": spec.test_id,
        "argv_sha256": sha256(
            json.dumps(
                list(spec.argv),
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest(),
        "expected_exit_code": spec.expected_exit_code,
        "stdout_contains": list(spec.stdout_contains),
        "stderr_contains": list(spec.stderr_contains),
        "setup_files": [
            {
                "path": item.path,
                "content_sha256": sha256(
                    item.content.encode("utf-8")
                ).hexdigest(),
            }
            for item in spec.setup_files
        ],
        "file_expectations": [
            {
                "path": item.path,
                "must_exist": item.must_exist,
                "exact_text_sha256": (
                    sha256(item.exact_text.encode("utf-8")).hexdigest()
                    if item.exact_text is not None
                    else None
                ),
            }
            for item in spec.file_expectations
        ],
        "timeout_seconds": spec.timeout_seconds,
    }
    raw = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(raw.encode("utf-8")).hexdigest()


def _evidence_ref(observation: dict[str, object]) -> str:
    payload = json.dumps(
        observation,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = sha256(payload.encode("utf-8")).hexdigest()
    return f"replay-exec-sha256:{digest}"
