from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
from pathlib import Path
from typing import Any
import argparse
import json

from .models import MEMORY_SCHEMA_VERSION, MemoryRecord
from .port import MemoryPort
from .sqlite import SQLiteMemoryPort

ARCHIVE_SCHEMA_VERSION = 1


def record_to_dict(record: MemoryRecord) -> dict[str, Any]:
    value = asdict(record)
    value["evidence_refs"] = list(record.evidence_refs)
    return value


def record_from_dict(raw: dict[str, Any]) -> MemoryRecord:
    if not isinstance(raw, dict):
        raise ValueError("memory record must be an object")

    evidence = raw.get("evidence_refs", [])
    if not isinstance(evidence, list):
        raise ValueError("evidence_refs must be a list")

    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        raise ValueError("metadata must be an object")

    try:
        return MemoryRecord(
            memory_id=str(raw["memory_id"]),
            kind=str(raw["kind"]),
            content=str(raw["content"]),
            source=str(raw["source"]),
            confidence=float(raw.get("confidence", 1.0)),
            metadata=dict(metadata),
            source_id=(
                str(raw["source_id"])
                if raw.get("source_id") is not None
                else None
            ),
            source_type=str(raw.get("source_type", "engine")),
            evidence_refs=tuple(str(item) for item in evidence),
            trust_class=str(raw.get("trust_class", "unknown")),
            importance=float(raw.get("importance", 0.5)),
            writer=str(raw.get("writer", "unknown")),
            validation_state=str(raw.get("validation_state", "committed")),
            created_at=float(raw.get("created_at", 0.0)),
            updated_at=float(raw.get("updated_at", 0.0)),
            schema_version=int(raw.get("schema_version", MEMORY_SCHEMA_VERSION)),
            invalidated=bool(raw.get("invalidated", False)),
        )
    except KeyError as exc:
        raise ValueError(f"memory record missing field: {exc.args[0]}") from exc


def build_memory_archive(memory: MemoryPort) -> dict[str, Any]:
    records = [record_to_dict(record) for record in memory.all()]
    return _archive_from_records(records)


def export_memory_archive(memory: MemoryPort, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    archive = build_memory_archive(memory)
    output.write_text(
        json.dumps(archive, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return output


def load_memory_archive(path: str | Path) -> dict[str, Any]:
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("memory archive is not valid JSON") from exc
    if not isinstance(raw, dict):
        raise ValueError("memory archive root must be an object")
    validate_memory_archive(raw)
    return raw


def validate_memory_archive(archive: dict[str, Any]) -> None:
    if archive.get("archive_schema_version") != ARCHIVE_SCHEMA_VERSION:
        raise ValueError("unsupported memory archive schema")
    records = archive.get("records")
    if not isinstance(records, list):
        raise ValueError("memory archive records must be a list")
    if archive.get("record_count") != len(records):
        raise ValueError("memory archive record_count mismatch")

    expected = archive.get("records_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise ValueError("memory archive records_sha256 is invalid")
    actual = _records_checksum(records)
    if actual != expected:
        raise ValueError("memory archive checksum mismatch")

    ids: set[str] = set()
    for raw_record in records:
        record = record_from_dict(raw_record)
        if record.memory_id in ids:
            raise ValueError(f"duplicate memory id in archive: {record.memory_id}")
        ids.add(record.memory_id)


def restore_memory_archive(
    memory: MemoryPort,
    archive_or_path: dict[str, Any] | str | Path,
    *,
    overwrite: bool = False,
) -> int:
    archive = (
        archive_or_path
        if isinstance(archive_or_path, dict)
        else load_memory_archive(archive_or_path)
    )
    validate_memory_archive(archive)

    records = [record_from_dict(item) for item in archive["records"]]
    existing_ids = {record.memory_id for record in memory.all()}
    conflicts = sorted(
        record.memory_id for record in records if record.memory_id in existing_ids
    )
    if conflicts and not overwrite:
        raise ValueError(
            "memory restore conflicts with existing ids: " + ", ".join(conflicts)
        )

    for record in records:
        memory.import_record(record, overwrite=overwrite)
    return len(records)


def _archive_from_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "archive_schema_version": ARCHIVE_SCHEMA_VERSION,
        "memory_schema_version": MEMORY_SCHEMA_VERSION,
        "record_count": len(records),
        "records_sha256": _records_checksum(records),
        "records": records,
    }


def _records_checksum(records: list[dict[str, Any]]) -> str:
    encoded = json.dumps(
        records,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="yisang-memory-archive",
        description="Export or restore YiSang authoritative memory archives.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    export = subparsers.add_parser("export")
    export.add_argument("--db", required=True)
    export.add_argument("--output", required=True)

    restore = subparsers.add_parser("restore")
    restore.add_argument("--db", required=True)
    restore.add_argument("--input", required=True)
    restore.add_argument("--overwrite", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "export":
        with SQLiteMemoryPort(args.db) as memory:
            path = export_memory_archive(memory, args.output)
        print(path)
        return 0

    if args.command == "restore":
        with SQLiteMemoryPort(args.db) as memory:
            restored = restore_memory_archive(
                memory,
                args.input,
                overwrite=args.overwrite,
            )
        print(f"restored={restored}")
        return 0

    raise AssertionError("unreachable")


if __name__ == "__main__":
    raise SystemExit(main())
