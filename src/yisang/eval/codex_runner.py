from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Iterable
import argparse
import json
import os
import re
import shutil
import subprocess

from .codex_matrix import DEFAULT_CODEX_V031_MATRIX, CodexEvalCase
from .repeatability import RunMetrics

_TOKEN_RE = re.compile(r"tokens used\s*\n?\s*([0-9][0-9,]*)", re.IGNORECASE)
_PARSE_ERROR_MARKER = "failed to parse function arguments"


def run_codex_case(
    case: CodexEvalCase,
    *,
    codex_bin: str = "codex",
    codex_home: str | Path | None = None,
    workspace_root: str | Path | None = None,
    timeout_seconds: float = 180.0,
) -> RunMetrics:
    env = os.environ.copy()
    if codex_home is not None:
        env["CODEX_HOME"] = str(Path(codex_home))

    root = Path(workspace_root) if workspace_root is not None else None
    if root is not None:
        root.mkdir(parents=True, exist_ok=True)

    started = perf_counter()
    try:
        with TemporaryDirectory(
            prefix=f"yisang-{case.case_id}-",
            dir=str(root) if root is not None else None,
        ) as temp_dir:
            workdir = Path(temp_dir)
            _initialize_workspace(workdir, case)
            completed = subprocess.run(
                [
                    codex_bin,
                    "exec",
                    "-s",
                    "workspace-write",
                    "-C",
                    str(workdir),
                    "-",
                ],
                input=case.prompt,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
                env=env,
                check=False,
            )
            latency_ms = (perf_counter() - started) * 1000
            combined = _combined_output(completed.stdout, completed.stderr)
            tool_calls = count_tool_calls(combined)
            malformed = combined.lower().count(_PARSE_ERROR_MARKER)
            context_tokens = parse_tokens_used(combined)
            verified, verification_error = verify_case(
                case,
                workdir,
                process_returncode=completed.returncode,
                combined_output=combined,
                tool_calls=tool_calls,
            )
            duplicates = (
                max(0, tool_calls - case.max_tool_calls)
                if case.max_tool_calls is not None
                and case.verifier == "stop_after_success"
                else 0
            )
            completion_after_success = (
                verified and duplicates == 0
                if case.verifier == "stop_after_success"
                else None
            )
            error = verification_error
            if completed.returncode != 0:
                process_error = f"codex_exit_code={completed.returncode}"
                error = f"{error}; {process_error}" if error else process_error

            return RunMetrics(
                success=verified and completed.returncode == 0,
                tool_calls=tool_calls,
                malformed_tool_calls=malformed,
                retries=count_retries(combined),
                completion_after_success=completion_after_success,
                latency_ms=latency_ms,
                context_tokens=context_tokens,
                duplicate_side_effects=duplicates,
                error=error,
            )
    except (subprocess.SubprocessError, OSError) as exc:
        return RunMetrics(
            success=False,
            latency_ms=(perf_counter() - started) * 1000,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_matrix(
    cases: Iterable[CodexEvalCase] = DEFAULT_CODEX_V031_MATRIX,
    *,
    repetitions: int,
    codex_bin: str = "codex",
    codex_home: str | Path | None = None,
    workspace_root: str | Path | None = None,
    timeout_seconds: float = 180.0,
) -> list[tuple[str, RunMetrics]]:
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")

    results: list[tuple[str, RunMetrics]] = []
    for case in cases:
        for _ in range(repetitions):
            result = run_codex_case(
                case,
                codex_bin=codex_bin,
                codex_home=codex_home,
                workspace_root=workspace_root,
                timeout_seconds=timeout_seconds,
            )
            results.append((case.case_id, result))
    return results


def write_jsonl(
    path: str | Path,
    results: Iterable[tuple[str, RunMetrics]],
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for case_id, metrics in results:
        record = {"case_id": case_id, **asdict(metrics)}
        lines.append(json.dumps(record, ensure_ascii=False))
    output.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output


def verify_case(
    case: CodexEvalCase,
    workdir: Path,
    *,
    process_returncode: int,
    combined_output: str,
    tool_calls: int,
) -> tuple[bool, str | None]:
    if case.verifier == "command_success":
        if process_returncode != 0:
            return False, f"command process exited {process_returncode}"
        if case.expected_text and case.expected_text not in combined_output:
            return False, f"expected response marker missing: {case.expected_text}"
        if case.max_tool_calls is not None and tool_calls > case.max_tool_calls:
            return False, "tool call budget exceeded"
        return True, None

    if case.expected_path is None:
        return False, "case is missing expected_path"

    target = workdir / case.expected_path
    if case.verifier == "directory_exists":
        if not target.is_dir():
            return False, f"directory not found: {case.expected_path}"
        return True, None

    if case.verifier in {
        "file_exact",
        "expected_failure_then_recovery",
        "stop_after_success",
    }:
        if not target.is_file():
            return False, f"file not found: {case.expected_path}"
        actual = target.read_text(encoding="utf-8")
        if case.expected_text is not None and actual != case.expected_text:
            return False, (
                f"file content mismatch for {case.expected_path}: "
                f"expected={case.expected_text!r} actual={actual!r}"
            )
        if case.max_tool_calls is not None and tool_calls > case.max_tool_calls:
            return False, "tool call budget exceeded"
        return True, None

    return False, f"unknown verifier: {case.verifier}"


def count_tool_calls(output: str) -> int:
    known = {"exec", "apply_patch"}
    return sum(1 for line in output.splitlines() if line.strip() in known)


def count_retries(output: str) -> int:
    return sum(
        1
        for line in output.splitlines()
        if "retry" in line.lower() or "retrying" in line.lower()
    )


def parse_tokens_used(output: str) -> int:
    matches = _TOKEN_RE.findall(output)
    if not matches:
        return 0
    return int(matches[-1].replace(",", ""))


def _initialize_workspace(workdir: Path, case: CodexEvalCase) -> None:
    for relative_path, content in case.setup_files.items():
        path = workdir / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    git = shutil.which("git")
    if git is not None:
        subprocess.run(
            [git, "init", "-q"],
            cwd=workdir,
            text=True,
            capture_output=True,
            check=False,
        )


def _combined_output(stdout: str | None, stderr: str | None) -> str:
    return "\n".join(part for part in (stdout or "", stderr or "") if part)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-codex",
        description="Run the YiSang v0.3.1 Codex E2E repeatability matrix.",
    )
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--codex-bin", default="codex")
    parser.add_argument("--codex-home")
    parser.add_argument("--workspace-root")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--case",
        action="append",
        dest="case_ids",
        help="Run only this case id; may be repeated.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    selected = DEFAULT_CODEX_V031_MATRIX
    if args.case_ids:
        wanted = set(args.case_ids)
        selected = tuple(case for case in selected if case.case_id in wanted)
        missing = wanted - {case.case_id for case in selected}
        if missing:
            raise SystemExit(f"unknown case id(s): {', '.join(sorted(missing))}")

    results = run_matrix(
        selected,
        repetitions=args.repetitions,
        codex_bin=args.codex_bin,
        codex_home=args.codex_home,
        workspace_root=args.workspace_root,
        timeout_seconds=args.timeout_seconds,
    )
    output = write_jsonl(args.output, results)
    successes = sum(1 for _, result in results if result.success)
    print(output)
    print(f"runs={len(results)} successes={successes}")
    return 0 if successes == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
