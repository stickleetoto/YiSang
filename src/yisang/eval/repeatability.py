from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Callable, Iterable
import argparse
import json


@dataclass(frozen=True)
class RunMetrics:
    success: bool
    tool_calls: int = 0
    malformed_tool_calls: int = 0
    retries: int = 0
    completion_after_success: bool | None = None
    latency_ms: float = 0.0
    context_tokens: int = 0
    duplicate_side_effects: int = 0
    error: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "tool_calls",
            "malformed_tool_calls",
            "retries",
            "context_tokens",
            "duplicate_side_effects",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must be non-negative")


@dataclass(frozen=True)
class CaseMetrics:
    case_id: str
    runs: int
    successes: int
    success_rate: float
    tool_calls_mean: float
    malformed_tool_call_rate: float
    retries_mean: float
    completion_after_success_rate: float | None
    latency_ms_p50: float
    latency_ms_p95: float
    context_tokens_mean: float
    duplicate_side_effects: int
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class RepeatabilityReport:
    schema_version: int
    cases: tuple[CaseMetrics, ...]

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "cases": [asdict(case) for case in self.cases],
            "summary": {
                "case_count": len(self.cases),
                "run_count": sum(case.runs for case in self.cases),
                "duplicate_side_effects": sum(
                    case.duplicate_side_effects for case in self.cases
                ),
                "minimum_success_rate": min(
                    (case.success_rate for case in self.cases),
                    default=0.0,
                ),
            },
        }


@dataclass(frozen=True)
class BaselineGate:
    passed: bool
    min_success_rate: float
    failed_cases: tuple[str, ...]
    duplicate_side_effects: int


def run_case(
    case_id: str,
    runner: Callable[[], RunMetrics],
    *,
    repetitions: int,
) -> CaseMetrics:
    if not case_id.strip():
        raise ValueError("case_id must be non-empty")
    if repetitions <= 0:
        raise ValueError("repetitions must be positive")

    runs: list[RunMetrics] = []
    for _ in range(repetitions):
        started = perf_counter()
        result = runner()
        elapsed_ms = (perf_counter() - started) * 1000
        if result.latency_ms == 0:
            result = replace(result, latency_ms=elapsed_ms)
        runs.append(result)
    return aggregate_case(case_id, runs)


def aggregate_case(case_id: str, runs: Iterable[RunMetrics]) -> CaseMetrics:
    items = list(runs)
    if not items:
        raise ValueError("at least one run is required")

    successes = sum(1 for item in items if item.success)
    completion_values = [
        item.completion_after_success
        for item in items
        if item.completion_after_success is not None
    ]
    total_tool_calls = sum(item.tool_calls for item in items)
    malformed_total = sum(item.malformed_tool_calls for item in items)
    latencies = sorted(item.latency_ms for item in items)

    return CaseMetrics(
        case_id=case_id,
        runs=len(items),
        successes=successes,
        success_rate=successes / len(items),
        tool_calls_mean=mean(item.tool_calls for item in items),
        malformed_tool_call_rate=(
            malformed_total / total_tool_calls if total_tool_calls else 0.0
        ),
        retries_mean=mean(item.retries for item in items),
        completion_after_success_rate=(
            sum(bool(value) for value in completion_values) / len(completion_values)
            if completion_values
            else None
        ),
        latency_ms_p50=_percentile(latencies, 0.50),
        latency_ms_p95=_percentile(latencies, 0.95),
        context_tokens_mean=mean(item.context_tokens for item in items),
        duplicate_side_effects=sum(item.duplicate_side_effects for item in items),
        errors=tuple(item.error for item in items if item.error),
    )


def build_report(grouped_runs: dict[str, list[RunMetrics]]) -> RepeatabilityReport:
    return RepeatabilityReport(
        schema_version=1,
        cases=tuple(
            aggregate_case(case_id, grouped_runs[case_id])
            for case_id in sorted(grouped_runs)
        ),
    )


def evaluate_baseline(
    report: RepeatabilityReport,
    *,
    min_success_rate: float = 0.90,
    require_no_duplicate_side_effects: bool = True,
) -> BaselineGate:
    if not 0 <= min_success_rate <= 1:
        raise ValueError("min_success_rate must be between 0 and 1")

    failed_cases = tuple(
        case.case_id
        for case in report.cases
        if case.success_rate < min_success_rate
    )
    duplicates = sum(case.duplicate_side_effects for case in report.cases)
    passed = not failed_cases and (
        not require_no_duplicate_side_effects or duplicates == 0
    )
    return BaselineGate(
        passed=passed,
        min_success_rate=min_success_rate,
        failed_cases=failed_cases,
        duplicate_side_effects=duplicates,
    )


def load_jsonl(path: str | Path) -> dict[str, list[RunMetrics]]:
    grouped: dict[str, list[RunMetrics]] = {}
    for line_number, raw_line in enumerate(
        Path(path).read_text(encoding="utf-8").splitlines(),
        start=1,
    ):
        line = raw_line.strip()
        if not line:
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {line_number}") from exc
        if not isinstance(raw, dict):
            raise ValueError(f"line {line_number} must contain a JSON object")
        case_id = raw.pop("case_id", None)
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"line {line_number} is missing case_id")
        try:
            metrics = RunMetrics(**raw)
        except TypeError as exc:
            raise ValueError(f"invalid metrics on line {line_number}: {exc}") from exc
        grouped.setdefault(case_id, []).append(metrics)
    if not grouped:
        raise ValueError("input contains no runs")
    return grouped


def write_report(path: str | Path, report: RepeatabilityReport) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return values[0]
    index = (len(values) - 1) * fraction
    lower = int(index)
    upper = min(lower + 1, len(values) - 1)
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-eval-repeatability",
        description="Aggregate repeated YiSang E2E runs and evaluate the v0.3.1 baseline.",
    )
    parser.add_argument("--input", required=True, help="JSONL run metrics")
    parser.add_argument("--output", required=True, help="JSON report path")
    parser.add_argument("--min-success-rate", type=float, default=0.90)
    parser.add_argument(
        "--allow-duplicate-side-effects",
        action="store_true",
        help="Do not fail the baseline gate when duplicate side effects are recorded.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    report = build_report(load_jsonl(args.input))
    output = write_report(args.output, report)
    gate = evaluate_baseline(
        report,
        min_success_rate=args.min_success_rate,
        require_no_duplicate_side_effects=not args.allow_duplicate_side_effects,
    )
    print(output)
    print(
        json.dumps(
            {
                "passed": gate.passed,
                "min_success_rate": gate.min_success_rate,
                "failed_cases": list(gate.failed_cases),
                "duplicate_side_effects": gate.duplicate_side_effects,
            },
            ensure_ascii=False,
        )
    )
    return 0 if gate.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
