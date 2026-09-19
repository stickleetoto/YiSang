from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .models import MEMORY_SCHEMA_VERSION, MemoryProposal, MemoryRecord
from .port import MemoryPort

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]+")


def _terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}


class SQLiteMemoryPort(MemoryPort):
    """Standalone authoritative memory backend.

    Read-side indexes may be added later, but this table remains the durable
    source of truth. Schema upgrades are additive so existing v0.3 databases
    can be opened in place.

    The model server is threaded, so one SQLite connection may be used from
    request-handler threads different from the thread that created the port.
    SQLite access is serialized through an RLock.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    memory_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL,
                    content TEXT NOT NULL,
                    source TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    metadata_json TEXT NOT NULL,
                    source_id TEXT,
                    source_type TEXT NOT NULL DEFAULT 'engine',
                    evidence_json TEXT NOT NULL DEFAULT '[]',
                    trust_class TEXT NOT NULL DEFAULT 'unknown',
                    importance REAL NOT NULL DEFAULT 0.5,
                    writer TEXT NOT NULL DEFAULT 'unknown',
                    validation_state TEXT NOT NULL DEFAULT 'committed',
                    created_at REAL NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL DEFAULT 0,
                    schema_version INTEGER NOT NULL DEFAULT 2,
                    invalidated INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_v2_columns()
            self._migrate_legacy_rows()
            self._conn.commit()

    def _ensure_v2_columns(self) -> None:
        existing = {
            row["name"]
            for row in self._conn.execute("PRAGMA table_info(memories)").fetchall()
        }
        columns = {
            "source_id": "TEXT",
            "source_type": "TEXT NOT NULL DEFAULT 'engine'",
            "evidence_json": "TEXT NOT NULL DEFAULT '[]'",
            "trust_class": "TEXT NOT NULL DEFAULT 'unknown'",
            "importance": "REAL NOT NULL DEFAULT 0.5",
            "writer": "TEXT NOT NULL DEFAULT 'unknown'",
            "validation_state": "TEXT NOT NULL DEFAULT 'committed'",
            "created_at": "REAL NOT NULL DEFAULT 0",
            "updated_at": "REAL NOT NULL DEFAULT 0",
            "schema_version": (
                f"INTEGER NOT NULL DEFAULT {MEMORY_SCHEMA_VERSION}"
            ),
            "invalidated": "INTEGER NOT NULL DEFAULT 0",
        }
        for name, definition in columns.items():
            if name not in existing:
                self._conn.execute(
                    f"ALTER TABLE memories ADD COLUMN {name} {definition}"
                )

    def _migrate_legacy_rows(self) -> None:
        rows = self._conn.execute(
            """
            SELECT memory_id, source, metadata_json, evidence_json,
                   writer, created_at, updated_at
            FROM memories
            """
        ).fetchall()
        for row in rows:
            metadata = _decode_json_object(row["metadata_json"])
            evidence = _decode_json_list(row["evidence_json"])
            legacy_evidence = metadata.get("evidence")
            if not evidence and isinstance(legacy_evidence, list):
                evidence = [str(item) for item in legacy_evidence]

            committed_at = metadata.get("committed_at")
            timestamp = (
                float(committed_at)
                if isinstance(committed_at, (int, float))
                else 0.0
            )
            created_at = float(row["created_at"] or 0.0)
            updated_at = float(row["updated_at"] or 0.0)
            writer = str(row["writer"] or "unknown")
            if writer == "unknown":
                writer = str(row["source"])

            self._conn.execute(
                """
                UPDATE memories
                SET evidence_json = ?,
                    writer = ?,
                    created_at = ?,
                    updated_at = ?,
                    schema_version = ?
                WHERE memory_id = ?
                """,
                (
                    json.dumps(evidence, ensure_ascii=False),
                    writer,
                    created_at or timestamp,
                    updated_at or timestamp,
                    MEMORY_SCHEMA_VERSION,
                    row["memory_id"],
                ),
            )

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        query_terms = _terms(query)
        if not query_terms:
            return []

        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self.all():
            if record.invalidated:
                continue
            record_terms = _terms(record.content)
            overlap = len(query_terms & record_terms)
            if overlap == 0:
                continue
            score = (
                float(overlap)
                + max(0.0, min(1.0, record.confidence)) * 0.10
                + max(0.0, min(1.0, record.importance)) * 0.05
            )
            ranked.append((score, record))

        ranked.sort(key=lambda item: (-item[0], item[1].memory_id))
        return [record for _, record in ranked[:limit]]

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = proposal.to_record()
        with self._lock:
            self._insert_record(record)
            self._conn.commit()
        return record

    def import_record(
        self,
        record: MemoryRecord,
        *,
        overwrite: bool = False,
    ) -> MemoryRecord:
        with self._lock:
            exists = self._conn.execute(
                "SELECT 1 FROM memories WHERE memory_id = ?",
                (record.memory_id,),
            ).fetchone()
            if exists is not None:
                if not overwrite:
                    raise ValueError(f"memory already exists: {record.memory_id}")
                self._conn.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (record.memory_id,),
                )
            self._insert_record(record)
            self._conn.commit()
        return record

    def _insert_record(self, record: MemoryRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO memories (
                memory_id, kind, content, source, confidence, metadata_json,
                source_id, source_type, evidence_json, trust_class,
                importance, writer, validation_state, created_at, updated_at,
                schema_version, invalidated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record.memory_id,
                record.kind,
                record.content,
                record.source,
                record.confidence,
                json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                record.source_id,
                record.source_type,
                json.dumps(
                    list(record.evidence_refs),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                record.trust_class,
                record.importance,
                record.writer,
                record.validation_state,
                record.created_at,
                record.updated_at,
                record.schema_version,
                int(record.invalidated),
            ),
        )

    def all(self) -> list[MemoryRecord]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT memory_id, kind, content, source, confidence, metadata_json,
                       source_id, source_type, evidence_json, trust_class,
                       importance, writer, validation_state, created_at, updated_at,
                       schema_version, invalidated
                FROM memories
                ORDER BY rowid ASC
                """
            ).fetchall()

        return [_record_from_row(row) for row in rows]

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteMemoryPort":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _record_from_row(row: sqlite3.Row) -> MemoryRecord:
    return MemoryRecord(
        memory_id=row["memory_id"],
        kind=row["kind"],
        content=row["content"],
        source=row["source"],
        confidence=float(row["confidence"]),
        metadata=_decode_json_object(row["metadata_json"]),
        source_id=row["source_id"],
        source_type=str(row["source_type"]),
        evidence_refs=tuple(_decode_json_list(row["evidence_json"])),
        trust_class=str(row["trust_class"]),
        importance=float(row["importance"]),
        writer=str(row["writer"]),
        validation_state=str(row["validation_state"]),
        created_at=float(row["created_at"]),
        updated_at=float(row["updated_at"]),
        schema_version=int(row["schema_version"]),
        invalidated=bool(row["invalidated"]),
    )


def _decode_json_object(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, str):
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _decode_json_list(raw: Any) -> list[str]:
    if not isinstance(raw, str):
        return []
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]
