from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from threading import RLock
from typing import Any

from .lifecycle import MemoryMutation, new_memory_mutation
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
            self._ensure_mutation_schema()
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

    def _ensure_mutation_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_mutations (
                mutation_id TEXT PRIMARY KEY,
                memory_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                actor TEXT NOT NULL,
                reason TEXT NOT NULL,
                created_at REAL NOT NULL,
                evidence_json TEXT NOT NULL,
                before_sha256 TEXT,
                after_sha256 TEXT,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self._conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_mutations_memory
            ON memory_mutations(memory_id, created_at)
            """
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
            self._insert_mutation(
                new_memory_mutation(
                    memory_id=record.memory_id,
                    operation="commit",
                    actor=record.writer or record.source,
                    reason="governed_commit",
                    evidence_refs=record.evidence_refs,
                    after=record,
                )
            )
            self._conn.commit()
        return record

    def import_record(
        self,
        record: MemoryRecord,
        *,
        overwrite: bool = False,
    ) -> MemoryRecord:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT memory_id, kind, content, source, confidence, metadata_json,
                       source_id, source_type, evidence_json, trust_class,
                       importance, writer, validation_state, created_at, updated_at,
                       schema_version, invalidated
                FROM memories
                WHERE memory_id = ?
                """,
                (record.memory_id,),
            ).fetchone()
            existing = _record_from_row(row) if row is not None else None
            if existing is not None:
                if not overwrite:
                    raise ValueError(f"memory already exists: {record.memory_id}")
                self._conn.execute(
                    "DELETE FROM memories WHERE memory_id = ?",
                    (record.memory_id,),
                )
            self._insert_record(record)
            self._insert_mutation(
                new_memory_mutation(
                    memory_id=record.memory_id,
                    operation="import_overwrite" if existing is not None else "import",
                    actor=record.writer or "restore",
                    reason="authoritative_restore",
                    evidence_refs=record.evidence_refs,
                    before=existing,
                    after=record,
                )
            )
            self._conn.commit()
        return record

    def mutations(self, memory_id: str | None = None) -> list[MemoryMutation]:
        with self._lock:
            if memory_id is None:
                rows = self._conn.execute(
                    """
                    SELECT mutation_id, memory_id, operation, actor, reason,
                           created_at, evidence_json, before_sha256, after_sha256,
                           metadata_json
                    FROM memory_mutations
                    ORDER BY created_at ASC, mutation_id ASC
                    """
                ).fetchall()
            else:
                rows = self._conn.execute(
                    """
                    SELECT mutation_id, memory_id, operation, actor, reason,
                           created_at, evidence_json, before_sha256, after_sha256,
                           metadata_json
                    FROM memory_mutations
                    WHERE memory_id = ?
                    ORDER BY created_at ASC, mutation_id ASC
                    """,
                    (memory_id,),
                ).fetchall()
        return [_mutation_from_row(row) for row in rows]

    def invalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        return self._set_invalidated(
            memory_id,
            invalidated=True,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )

    def revalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        return self._set_invalidated(
            memory_id,
            invalidated=False,
            actor=actor,
            reason=reason,
            evidence_refs=evidence_refs,
        )

    def _set_invalidated(
        self,
        memory_id: str,
        *,
        invalidated: bool,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...],
    ) -> MemoryRecord:
        if not actor.strip():
            raise ValueError("actor must be non-empty")
        if not reason.strip():
            raise ValueError("reason must be non-empty")

        with self._lock:
            row = self._conn.execute(
                """
                SELECT memory_id, kind, content, source, confidence, metadata_json,
                       source_id, source_type, evidence_json, trust_class,
                       importance, writer, validation_state, created_at, updated_at,
                       schema_version, invalidated
                FROM memories
                WHERE memory_id = ?
                """,
                (memory_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"memory not found: {memory_id}")

            current = _record_from_row(row)
            if current.invalidated == invalidated:
                return current

            import time
            updated = MemoryRecord(
                memory_id=current.memory_id,
                kind=current.kind,
                content=current.content,
                source=current.source,
                confidence=current.confidence,
                metadata=dict(current.metadata),
                source_id=current.source_id,
                source_type=current.source_type,
                evidence_refs=tuple(current.evidence_refs),
                trust_class=current.trust_class,
                importance=current.importance,
                writer=current.writer,
                validation_state="invalidated" if invalidated else "committed",
                created_at=current.created_at,
                updated_at=time.time(),
                schema_version=current.schema_version,
                invalidated=invalidated,
            )
            self._conn.execute(
                """
                UPDATE memories
                SET validation_state = ?, updated_at = ?, invalidated = ?
                WHERE memory_id = ?
                """,
                (
                    updated.validation_state,
                    updated.updated_at,
                    int(updated.invalidated),
                    memory_id,
                ),
            )
            self._insert_mutation(
                new_memory_mutation(
                    memory_id=memory_id,
                    operation="invalidate" if invalidated else "revalidate",
                    actor=actor,
                    reason=reason,
                    evidence_refs=evidence_refs,
                    before=current,
                    after=updated,
                )
            )
            self._conn.commit()
            return updated

    def _insert_mutation(self, mutation: MemoryMutation) -> None:
        self._conn.execute(
            """
            INSERT INTO memory_mutations (
                mutation_id, memory_id, operation, actor, reason, created_at,
                evidence_json, before_sha256, after_sha256, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mutation.mutation_id,
                mutation.memory_id,
                mutation.operation,
                mutation.actor,
                mutation.reason,
                mutation.created_at,
                json.dumps(list(mutation.evidence_refs), ensure_ascii=False),
                mutation.before_sha256,
                mutation.after_sha256,
                json.dumps(mutation.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )

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


def _mutation_from_row(row: sqlite3.Row) -> MemoryMutation:
    return MemoryMutation(
        mutation_id=str(row["mutation_id"]),
        memory_id=str(row["memory_id"]),
        operation=str(row["operation"]),
        actor=str(row["actor"]),
        reason=str(row["reason"]),
        created_at=float(row["created_at"]),
        evidence_refs=tuple(_decode_json_list(row["evidence_json"])),
        before_sha256=(
            str(row["before_sha256"])
            if row["before_sha256"] is not None
            else None
        ),
        after_sha256=(
            str(row["after_sha256"])
            if row["after_sha256"] is not None
            else None
        ),
        metadata=_decode_json_object(row["metadata_json"]),
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
