from __future__ import annotations

from dataclasses import asdict, dataclass, field
from math import ceil
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
    expected_knowledge_refs: tuple[str, ...] = ()


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
    library_preserved: bool = True
    source_expected_knowledge_retrieved: bool = True
    expected_knowledge_retrieved: bool = True
    source_used_knowledge_refs: tuple[str, ...] = ()
    used_knowledge_refs: tuple[str, ...] = ()


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
    library_factory=None,
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
    source_used_knowledge_refs = tuple(source_response.used_knowledge_refs)
    source_engine_used = source_response.engine_id == source_engine
    source_expected_memory_retrieved = set(
        probe.expected_memory_ids
    ).issubset(source_used_memory_ids)
    source_expected_ego_selected = set(
        probe.expected_ego_ids
    ).issubset(source_used_ego_ids)
    source_expected_knowledge_retrieved = set(
        probe.expected_knowledge_refs
    ).issubset(source_used_knowledge_refs)

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
        library_factory=library_factory,
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
    library_preserved = source_snapshot.library == restored_snapshot.library
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
    used_knowledge_refs = tuple(response.used_knowledge_refs)
    target_engine_used = response.engine_id == target_engine
    expected_memory_retrieved = set(probe.expected_memory_ids).issubset(
        used_memory_ids
    )
    expected_ego_selected = set(probe.expected_ego_ids).issubset(
        used_ego_ids
    )
    expected_knowledge_retrieved = set(
        probe.expected_knowledge_refs
    ).issubset(used_knowledge_refs)

    passed = all(
        (
            identity_preserved,
            goal_preserved,
            state_preserved,
            memory_preserved,
            capabilities_preserved,
            library_preserved,
            continuity_preserved,
            source_engine_used,
            target_engine_used,
            source_expected_memory_retrieved,
            source_expected_ego_selected,
            source_expected_knowledge_retrieved,
            expected_memory_retrieved,
            expected_ego_selected,
            expected_knowledge_retrieved,
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
        library_preserved=library_preserved,
        source_expected_knowledge_retrieved=source_expected_knowledge_retrieved,
        expected_knowledge_retrieved=expected_knowledge_retrieved,
        source_used_knowledge_refs=source_used_knowledge_refs,
        used_knowledge_refs=used_knowledge_refs,
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


def evaluate_v06_closeout(
    report: ContinuityReport,
    *,
    min_repeats: int = 3,
) -> ContinuityCloseoutCheck:
    base = evaluate_v05_closeout(report, min_repeats=min_repeats)
    errors = list(base.errors)

    if report.metadata.get("library_probe") is not True:
        errors.append("library_probe evidence is missing")

    for case in report.cases:
        if not case.library_preserved:
            errors.append(f"{case.case_id}: Library snapshot was not preserved")
        if not case.source_expected_knowledge_retrieved:
            errors.append(
                f"{case.case_id}: source Library knowledge was not retrieved"
            )
        if not case.expected_knowledge_retrieved:
            errors.append(
                f"{case.case_id}: restored Library knowledge was not retrieved"
            )
        if not case.source_used_knowledge_refs:
            errors.append(
                f"{case.case_id}: source knowledge_ref evidence is missing"
            )
        if not case.used_knowledge_refs:
            errors.append(
                f"{case.case_id}: restored knowledge_ref evidence is missing"
            )

    return ContinuityCloseoutCheck(
        ready=not errors,
        errors=tuple(dict.fromkeys(errors)),
    )


def load_continuity_report(path: str | Path) -> ContinuityReport:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("continuity report is not valid JSON") from exc

    if not isinstance(raw, dict):
        raise ValueError("continuity report root must be an object")
    if raw.get("schema_version") != 1:
        raise ValueError("unsupported continuity report schema")

    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("continuity report metadata must be an object")

    case_items = raw.get("cases")
    if not isinstance(case_items, list):
        raise ValueError("continuity report cases must be a list")

    cases: list[ContinuityCaseResult] = []
    for item in case_items:
        if not isinstance(item, dict):
            raise ValueError("continuity report case must be an object")
        try:
            cases.append(
                ContinuityCaseResult(
                    case_id=str(item["case_id"]),
                    source_engine=str(item["source_engine"]),
                    target_engine=str(item["target_engine"]),
                    passed=bool(item["passed"]),
                    identity_preserved=bool(item["identity_preserved"]),
                    goal_preserved=bool(item["goal_preserved"]),
                    state_preserved=bool(item["state_preserved"]),
                    memory_preserved=bool(item["memory_preserved"]),
                    capabilities_preserved=bool(item["capabilities_preserved"]),
                    continuity_fingerprint_preserved=bool(
                        item["continuity_fingerprint_preserved"]
                    ),
                    source_engine_used=bool(item["source_engine_used"]),
                    target_engine_used=bool(item["target_engine_used"]),
                    source_expected_memory_retrieved=bool(
                        item["source_expected_memory_retrieved"]
                    ),
                    source_expected_ego_selected=bool(
                        item["source_expected_ego_selected"]
                    ),
                    expected_memory_retrieved=bool(
                        item["expected_memory_retrieved"]
                    ),
                    expected_ego_selected=bool(item["expected_ego_selected"]),
                    restore_latency_ms=float(item["restore_latency_ms"]),
                    probe_latency_ms=float(item["probe_latency_ms"]),
                    source_fingerprint=str(item["source_fingerprint"]),
                    restored_fingerprint=str(item["restored_fingerprint"]),
                    source_used_memory_ids=tuple(
                        str(value)
                        for value in item.get("source_used_memory_ids", [])
                    ),
                    source_used_ego_ids=tuple(
                        str(value)
                        for value in item.get("source_used_ego_ids", [])
                    ),
                    used_memory_ids=tuple(
                        str(value) for value in item.get("used_memory_ids", [])
                    ),
                    used_ego_ids=tuple(
                        str(value) for value in item.get("used_ego_ids", [])
                    ),
                    source_response_text=str(
                        item.get("source_response_text", "")
                    ),
                    response_text=str(item.get("response_text", "")),
                    library_preserved=bool(
                        item.get("library_preserved", True)
                    ),
                    source_expected_knowledge_retrieved=bool(
                        item.get("source_expected_knowledge_retrieved", True)
                    ),
                    expected_knowledge_retrieved=bool(
                        item.get("expected_knowledge_retrieved", True)
                    ),
                    source_used_knowledge_refs=tuple(
                        str(value)
                        for value in item.get(
                            "source_used_knowledge_refs",
                            [],
                        )
                    ),
                    used_knowledge_refs=tuple(
                        str(value)
                        for value in item.get("used_knowledge_refs", [])
                    ),
                )
            )
        except KeyError as exc:
            raise ValueError(
                f"continuity report case missing field: {exc.args[0]}"
            ) from exc

    return ContinuityReport(
        schema_version=1,
        cases=tuple(cases),
        metadata={
            str(key): value
            for key, value in metadata.items()
            if isinstance(value, (str, int, float, bool)) or value is None
        },
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
    if fraction == 0.0:
        return ordered[0]
    rank = max(1, min(len(ordered), ceil(fraction * len(ordered))))
    return ordered[rank - 1]
