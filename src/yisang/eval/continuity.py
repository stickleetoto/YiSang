from __future__ import annotations

from dataclasses import asdict, dataclass
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

    @property
    def pass_rate(self) -> float:
        if not self.cases:
            return 0.0
        return sum(1 for case in self.cases if case.passed) / len(self.cases)

    @property
    def all_passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "case_count": len(self.cases),
            "pass_rate": self.pass_rate,
            "all_passed": self.all_passed,
            "cases": [asdict(case) for case in self.cases],
        }


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
) -> ContinuityReport:
    return ContinuityReport(
        schema_version=1,
        cases=tuple(cases),
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
