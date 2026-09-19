from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Iterable
import json

from yisang.core.models import YiSangRequest
from yisang.identity.bundle import (
    build_continuity_bundle,
    restore_continuity_bundle,
)
from yisang.identity.snapshot import (
    build_identity_snapshot,
    continuity_fingerprint,
)
from yisang.memory.port import MemoryPort


@dataclass(frozen=True)
class ContinuityProbe:
    request_text: str = "continuity probe"
    expected_memory_ids: tuple[str, ...] = ()
    expected_ego_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContinuityCaseResult:
    case_id: str
    source_engine: str
    target_engine: str
    passed: bool
    identity_preserved: bool
    goal_preserved: bool
    state_preserved: bool
    memory_preserved: bool
    capabilities_preserved: bool
    continuity_fingerprint_preserved: bool
    source_engine_used: bool
    target_engine_used: bool
    source_expected_memory_retrieved: bool
    source_expected_ego_selected: bool
    expected_memory_retrieved: bool
    expected_ego_selected: bool
    restore_latency_ms: float
    probe_latency_ms: float
    source_fingerprint: str
    restored_fingerprint: str
    source_used_memory_ids: tuple[str, ...]
    source_used_ego_ids: tuple[str, ...]
    used_memory_ids: tuple[str, ...]
    used_ego_ids: tuple[str, ...]
    source_response_text: str
    response_text: str


@dataclass(frozen=True)
class ContinuityReport:
    schema_version: int
    cases: tuple[ContinuityCaseResult, ...]
    metadata: dict[str, str | int | float | bool | None] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for case in self.cases if case.passed) / len(self.cases)

    @property
    def all_passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)

    def to_dict(self) -> dict:
        restore_latencies = [
            case.restore_latency_ms for case in self.cases
        ]
        probe_latencies = [
            case.probe_latency_ms for case in self.cases
        ]
        return {
            "schema_version": self.schema_version,
            "metadata": dict(self.metadata),
            "case_count": len(self.cases),
            "pass_rate": self.pass_rate,
            "all_passed": self.all_passed,
            "summary": {
                "mean_restore_latency_ms": _mean(restore_latencies),
                "p95_restore_latency_ms": _percentile(
                    restore_latencies,
                    0.95,
                ),
                "mean_probe_latency_ms": _mean(probe_latencies),
                "p95_probe_latency_ms": _percentile(
                    probe_latencies,
                    0.95,
                ),
            },
            "cases": [asdict(case) for case in self.cases],
        }


@dataclass(frozen=True)
class ContinuityCloseoutCheck:
    ready: bool
    errors: tuple[str, ...]


def run_continuity_case(
    *,
    case_id: str,
    source_runtime,
    target_runtime,
    target_engine: str,
    memory_factory,
    policy_version: str,
    runtime_version: str,
    probe: ContinuityProbe | None = None,
) -> ContinuityCaseResult:
    if not case_id.strip():
        raise ValueError("case_id must be non-empty")

    probe = probe or ContinuityProbe()
    source_engine = source_runtime.state.active_engine

    source_probe_started = perf_counter()
    source_response = source_runtime.run(
        YiSangRequest(
            request_id=f"continuity-source-{case_id}",
            text=probe.request_text,
            metadata={"continuity_probe": True, "continuity_side": "source"},
        )
    )
    source_probe_latency_ms = (perf_counter() - source_probe_started) * 1000

    source_used_memory_ids = tuple(source_response.used_memory_ids)
    source_used_ego_ids = tuple(source_response.used_ego_ids)
    source_engine_used = source_response.engine_id == source_engine
    source_expected_memory_retrieved = set(
        probe.expected_memory_ids
    ).issubset(source_used_memory_ids)
    source_expected_ego_selected = set(
        probe.expected_ego_ids
    ).issubset(source_used_ego_ids)

    bundle = build_continuity_bundle(
        source_runtime,
        policy_version=policy_version,
        runtime_version=runtime_version,
    )
    source_snapshot = bundle.snapshot
    source_fingerprint = continuity_fingerprint(source_snapshot)

    restore_started = perf_counter()
    restore_continuity_bundle(
        bundle,
        target_runtime,
        target_engine=target_engine,
        memory_factory=memory_factory,
    )
    restore_latency_ms = (perf_counter() - restore_started) * 1000

    restored_snapshot = build_identity_snapshot(
        target_runtime,
        policy_version=policy_version,
        runtime_version=runtime_version,
    )
    restored_fingerprint = continuity_fingerprint(restored_snapshot)

    source_state = source_snapshot.state
    restored_state = restored_snapshot.state

    identity_preserved = source_snapshot.agent_id == restored_snapshot.agent_id
    goal_preserved = (
        source_state.get("current_goal") == restored_state.get("current_goal")
        and source_snapshot.active_goals == restored_snapshot.active_goals
    )
    state_preserved = source_state == restored_state
    memory_preserved = source_snapshot.memory == restored_snapshot.memory
    capabilities_preserved = (
        source_snapshot.ego_registry == restored_snapshot.ego_registry
    )
    continuity_preserved = source_fingerprint == restored_fingerprint

    probe_started = perf_counter()
    response = target_runtime.run(
        YiSangRequest(
            request_id=f"continuity-{case_id}",
            text=probe.request_text,
            metadata={"continuity_probe": True},
        )
    )
    probe_latency_ms = (perf_counter() - probe_started) * 1000

    used_memory_ids = tuple(response.used_memory_ids)
    used_ego_ids = tuple(response.used_ego_ids)
    target_engine_used = response.engine_id == target_engine
    expected_memory_retrieved = set(probe.expected_memory_ids).issubset(
        used_memory_ids
    )
    expected_ego_selected = set(probe.expected_ego_ids).issubset(
        used_ego_ids
    )

    passed = all(
        (
            identity_preserved,
            goal_preserved,
            state_preserved,
            memory_preserved,
            capabilities_preserved,
            continuity_preserved,
            source_engine_used,
            target_engine_used,
            source_expected_memory_retrieved,
            source_expected_ego_selected,
            expected_memory_retrieved,
            expected_ego_selected,
        )
    )

    return ContinuityCaseResult(
        case_id=case_id,
        source_engine=source_engine,
        target_engine=target_engine,
        passed=passed,
        identity_preserved=identity_preserved,
        goal_preserved=goal_preserved,
        state_preserved=state_preserved,
        memory_preserved=memory_preserved,
        capabilities_preserved=capabilities_preserved,
        continuity_fingerprint_preserved=continuity_preserved,
        source_engine_used=source_engine_used,
        target_engine_used=target_engine_used,
        source_expected_memory_retrieved=source_expected_memory_retrieved,
        source_expected_ego_selected=source_expected_ego_selected,
        expected_memory_retrieved=expected_memory_retrieved,
        expected_ego_selected=expected_ego_selected,
        restore_latency_ms=restore_latency_ms,
        probe_latency_ms=source_probe_latency_ms + probe_latency_ms,
        source_fingerprint=source_fingerprint,
        restored_fingerprint=restored_fingerprint,
        source_used_memory_ids=source_used_memory_ids,
        source_used_ego_ids=source_used_ego_ids,
        used_memory_ids=used_memory_ids,
        used_ego_ids=used_ego_ids,
        source_response_text=source_response.text,
        response_text=response.text,
    )


def build_continuity_report(
    cases: Iterable[ContinuityCaseResult],
    *,
    metadata: dict[str, str | int | float | bool | None] | None = None,
) -> ContinuityReport:
    return ContinuityReport(
        schema_version=1,
        cases=tuple(cases),
        metadata=dict(metadata or {}),
    )


def evaluate_v05_closeout(
    report: ContinuityReport,
    *,
    min_repeats: int = 3,
) -> ContinuityCloseoutCheck:
    if min_repeats <= 0:
        raise ValueError("min_repeats must be positive")

    errors: list[str] = []
    if len(report.cases) < min_repeats:
        errors.append(
            f"continuity report needs at least {min_repeats} repeated cases"
        )
    if not report.all_passed:
        errors.append("not all continuity cases passed")

    source_family = report.metadata.get("source_family")
    target_family = report.metadata.get("target_family")
    if not isinstance(source_family, str) or not source_family.strip():
        errors.append("source_family evidence is missing")
    if not isinstance(target_family, str) or not target_family.strip():
        errors.append("target_family evidence is missing")
    if (
        isinstance(source_family, str)
        and isinstance(target_family, str)
        and source_family.strip()
        and target_family.strip()
        and source_family.strip().lower() == target_family.strip().lower()
    ):
        errors.append("source and target engine families must differ")

    source_model = report.metadata.get("source_model")
    target_model = report.metadata.get("target_model")
    if not isinstance(source_model, str) or not source_model.strip():
        errors.append("source_model evidence is missing")
    if not isinstance(target_model, str) or not target_model.strip():
        errors.append("target_model evidence is missing")

    for case in report.cases:
        if not case.source_engine_used:
            errors.append(f"{case.case_id}: source engine was not exercised")
        if not case.target_engine_used:
            errors.append(f"{case.case_id}: target engine was not exercised")
        if not case.continuity_fingerprint_preserved:
            errors.append(
                f"{case.case_id}: continuity fingerprint was not preserved"
            )

    return ContinuityCloseoutCheck(
        ready=not errors,
        errors=tuple(dict.fromkeys(errors)),
    )


def write_continuity_report(
    report: ContinuityReport,
    path: str | Path,
) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            report.to_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return output


def _mean(values: list[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def _percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    if not 0.0 <= fraction <= 1.0:
        raise ValueError("fraction must be between 0 and 1")
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int((len(ordered) - 1) * fraction)))
    return ordered[index]
