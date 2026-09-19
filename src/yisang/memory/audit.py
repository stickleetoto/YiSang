from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
import argparse
import json

from .models import MEMORY_SCHEMA_VERSION, TRUST_CLASSES, VALIDATION_STATES
from .port import MemoryPort
from .sqlite import SQLiteMemoryPort


@dataclass(frozen=True)
class MemoryAuditIssue:
    code: str
    memory_id: str | None
    detail: str
    severity: str = "error"


@dataclass(frozen=True)
class MemoryAuditReport:
    record_count: int
    active_count: int
    invalidated_count: int
    superseded_count: int
    mutation_count: int
    schema_versions: dict[int, int]
    issues: tuple[MemoryAuditIssue, ...]

    @property
    def ok(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_count": self.record_count,
            "active_count": self.active_count,
            "invalidated_count": self.invalidated_count,
            "superseded_count": self.superseded_count,
            "mutation_count": self.mutation_count,
            "schema_versions": {
                str(key): value for key, value in sorted(self.schema_versions.items())
            },
            "ok": self.ok,
            "issues": [asdict(issue) for issue in self.issues],
        }


def audit_memory(
    memory: MemoryPort,
    *,
    require_current_schema: bool = False,
) -> MemoryAuditReport:
    records = memory.all()
    ids = {record.memory_id for record in records}
    issues: list[MemoryAuditIssue] = []

    for record in records:
        if not record.evidence_refs:
            issues.append(
                MemoryAuditIssue(
                    "missing_provenance_evidence",
                    record.memory_id,
                    "durable record has no evidence_refs",
                )
            )
        if not record.source.strip() or record.source == "unknown":
            issues.append(
                MemoryAuditIssue(
                    "unknown_source",
                    record.memory_id,
                    "record source is missing or unknown",
                )
            )
        if not record.source_type.strip():
            issues.append(
                MemoryAuditIssue(
                    "missing_source_type",
                    record.memory_id,
                    "record source_type is empty",
                )
            )
        if not record.writer.strip() or record.writer == "unknown":
            issues.append(
                MemoryAuditIssue(
                    "unknown_writer",
                    record.memory_id,
                    "record writer is missing or unknown",
                )
            )
        if record.trust_class not in TRUST_CLASSES:
            issues.append(
                MemoryAuditIssue(
                    "invalid_trust_class",
                    record.memory_id,
                    f"unknown trust_class: {record.trust_class}",
                )
            )
        if record.validation_state not in VALIDATION_STATES:
            issues.append(
                MemoryAuditIssue(
                    "invalid_validation_state",
                    record.memory_id,
                    f"unknown validation_state: {record.validation_state}",
                )
            )
        if record.supersedes_id is not None and record.supersedes_id not in ids:
            issues.append(
                MemoryAuditIssue(
                    "dangling_supersedes",
                    record.memory_id,
                    f"supersedes missing memory: {record.supersedes_id}",
                )
            )
        if (
            record.superseded_by_id is not None
            and record.superseded_by_id not in ids
        ):
            issues.append(
                MemoryAuditIssue(
                    "dangling_superseded_by",
                    record.memory_id,
                    f"superseded_by missing memory: {record.superseded_by_id}",
                )
            )
        if record.validation_state == "superseded":
            if not record.invalidated:
                issues.append(
                    MemoryAuditIssue(
                        "superseded_not_invalidated",
                        record.memory_id,
                        "superseded record must be invalidated",
                    )
                )
            if record.valid_until is None:
                issues.append(
                    MemoryAuditIssue(
                        "superseded_without_valid_until",
                        record.memory_id,
                        "superseded record must have valid_until",
                    )
                )
            if record.superseded_by_id is None:
                issues.append(
                    MemoryAuditIssue(
                        "superseded_without_successor",
                        record.memory_id,
                        "superseded record must identify its successor",
                    )
                )
        if record.success_count < 0 or record.failure_count < 0:
            issues.append(
                MemoryAuditIssue(
                    "negative_usage_counter",
                    record.memory_id,
                    "usage outcome counters must be non-negative",
                )
            )
        if require_current_schema and record.schema_version != MEMORY_SCHEMA_VERSION:
            issues.append(
                MemoryAuditIssue(
                    "stale_schema",
                    record.memory_id,
                    (
                        f"record schema={record.schema_version}, "
                        f"current={MEMORY_SCHEMA_VERSION}"
                    ),
                )
            )

    try:
        mutations = memory.mutations()
    except NotImplementedError:
        mutations = []
        issues.append(
            MemoryAuditIssue(
                "mutation_history_unavailable",
                None,
                "backend does not expose mutation history",
                severity="warning",
            )
        )

    mutation_ids = {mutation.memory_id for mutation in mutations}
    for record in records:
        if record.memory_id not in mutation_ids:
            issues.append(
                MemoryAuditIssue(
                    "missing_mutation_history",
                    record.memory_id,
                    "record has no audit mutation entries",
                    severity="warning",
                )
            )

    schema_versions = Counter(record.schema_version for record in records)
    return MemoryAuditReport(
        record_count=len(records),
        active_count=sum(1 for record in records if record.is_active()),
        invalidated_count=sum(1 for record in records if record.invalidated),
        superseded_count=sum(
            1 for record in records if record.validation_state == "superseded"
        ),
        mutation_count=len(mutations),
        schema_versions=dict(schema_versions),
        issues=tuple(issues),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-memory-audit",
        description="Audit YiSang authoritative memory invariants.",
    )
    parser.add_argument("--db", required=True)
    parser.add_argument("--output")
    parser.add_argument("--require-current-schema", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    with SQLiteMemoryPort(args.db) as memory:
        report = audit_memory(
            memory,
            require_current_schema=args.require_current_schema,
        )
    payload = report.to_dict()
    rendered = json.dumps(payload, ensure_ascii=False, indent=2)

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered + "\n", encoding="utf-8")
        print(output)
    else:
        print(rendered)

    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
