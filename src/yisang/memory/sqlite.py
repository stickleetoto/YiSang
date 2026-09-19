from __future__ import annotations

from dataclasses import replace
import json
import sqlite3
import time
from pathlib import Path
from threading import RLock
from typing import Any

from .lexical import lexical_terms
from .lifecycle import MemoryMutation, new_memory_mutation
from .models import MEMORY_SCHEMA_VERSION, MemoryProposal, MemoryRecord
from .port import MemoryPort


class SQLiteMemoryPort(MemoryPort):
    """Standalone authoritative memory backend with additive schema upgrades."""

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
                    valid_from REAL NOT NULL DEFAULT 0,
                    valid_until REAL,
                    supersedes_id TEXT,
                    superseded_by_id TEXT,
                    last_used_at REAL,
                    success_count INTEGER NOT NULL DEFAULT 0,
                    failure_count INTEGER NOT NULL DEFAULT 0,
                    schema_version INTEGER NOT NULL DEFAULT 3,
                    invalidated INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._ensure_columns()
            self._ensure_mutation_schema()
            self._migrate_legacy_rows()
            self._conn.commit()

    def _ensure_columns(self) -> None:
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
            "valid_from": "REAL NOT NULL DEFAULT 0",
            "valid_until": "REAL",
            "supersedes_id": "TEXT",
            "superseded_by_id": "TEXT",
            "last_used_at": "REAL",
            "success_count": "INTEGER NOT NULL DEFAULT 0",
            "failure_count": "INTEGER NOT NULL DEFAULT 0",
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
                   writer, created_at, updated_at, valid_from
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
            valid_from = float(row["valid_from"] or 0.0)
            writer = str(row["writer"] or "unknown")
            if writer == "unknown":
                writer = str(row["source"])

            base_time = created_at or timestamp
            self._conn.execute(
                """
                UPDATE memories
                SET evidence_json = ?,
                    writer = ?,
                    created_at = ?,
                    updated_at = ?,
                    valid_from = ?,
                    schema_version = ?
                WHERE memory_id = ?
                """,
                (
                    json.dumps(evidence, ensure_ascii=False),
                    writer,
                    base_time,
                    updated_at or base_time,
                    valid_from or base_time,
                    MEMORY_SCHEMA_VERSION,
                    row["memory_id"],
                ),
            )

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        query_terms = lexical_terms(query)
        if not query_terms:
            return []

        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self.all():
            if not record.is_active():
                continue
            record_terms = lexical_terms(record.content)
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
        selected = [record for _, record in ranked[:limit]]
        self.mark_retrieved([record.memory_id for record in selected])
        return selected

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
            row = self._select_record(record.memory_id)
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

    def mark_retrieved(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = time.time()
        with self._lock:
            self._conn.executemany(
                "UPDATE memories SET last_used_at = ? WHERE memory_id = ?",
                [(now, memory_id) for memory_id in dict.fromkeys(memory_ids)],
            )
            self._conn.commit()

    def record_outcome(self, memory_ids: list[str], *, success: bool) -> None:
        if not memory_ids:
            return
        field = "success_count" if success else "failure_count"
        with self._lock:
            for memory_id in dict.fromkeys(memory_ids):
                self._conn.execute(
                    f"UPDATE memories SET {field} = {field} + 1 WHERE memory_id = ?",
                    (memory_id,),
                )
            self._conn.commit()

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

    def supersede(
        self,
        memory_id: str,
        *,
        superseded_by_id: str,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        if not actor.strip():
            raise ValueError("actor must be non-empty")
        if not reason.strip():
            raise ValueError("reason must be non-empty")
        with self._lock:
            row = self._select_record(memory_id)
            if row is None:
                raise KeyError(f"memory not found: {memory_id}")
            current = _record_from_row(row)
            if current.superseded_by_id == superseded_by_id:
                return current
            now = time.time()
            updated = replace(
                current,
                invalidated=True,
                validation_state="superseded",
                updated_at=now,
                valid_until=now,
                superseded_by_id=superseded_by_id,
            )
            self._update_record(updated)
            self._insert_mutation(
                new_memory_mutation(
                    memory_id=memory_id,
                    operation="supersede",
                    actor=actor,
                    reason=reason,
                    evidence_refs=evidence_refs,
                    before=current,
                    after=updated,
                    metadata={"superseded_by_id": superseded_by_id},
                )
            )
            self._conn.commit()
            return updated

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
            row = self._select_record(memory_id)
            if row is None:
                raise KeyError(f"memory not found: {memory_id}")

            current = _record_from_row(row)
            if current.invalidated == invalidated:
                return current

            updated = replace(
                current,
                invalidated=invalidated,
                validation_state="invalidated" if invalidated else "committed",
                updated_at=time.time(),
                valid_until=(
                    current.valid_until
                    if not invalidated
                    else current.valid_until
                ),
            )
            self._update_record(updated)
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

    def _select_record(self, memory_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            """
            SELECT memory_id, kind, content, source, confidence, metadata_json,
                   source_id, source_type, evidence_json, trust_class,
                   importance, writer, validation_state, created_at, updated_at,
                   valid_from, valid_until, supersedes_id, superseded_by_id,
                   last_used_at, success_count, failure_count,
                   schema_version, invalidated
            FROM memories
            WHERE memory_id = ?
            """,
            (memory_id,),
        ).fetchone()

    def _update_record(self, record: MemoryRecord) -> None:
        self._conn.execute(
            """
            UPDATE memories SET
                kind = ?, content = ?, source = ?, confidence = ?,
                metadata_json = ?, source_id = ?, source_type = ?,
                evidence_json = ?, trust_class = ?, importance = ?,
                writer = ?, validation_state = ?, created_at = ?, updated_at = ?,
                valid_from = ?, valid_until = ?, supersedes_id = ?,
                superseded_by_id = ?, last_used_at = ?, success_count = ?,
                failure_count = ?, schema_version = ?, invalidated = ?
            WHERE memory_id = ?
            """,
            (
                record.kind,
                record.content,
                record.source,
                record.confidence,
                json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
                record.source_id,
                record.source_type,
                json.dumps(list(record.evidence_refs), ensure_ascii=False),
                record.trust_class,
                record.importance,
                record.writer,
                record.validation_state,
                record.created_at,
                record.updated_at,
                record.valid_from,
                record.valid_until,
                record.supersedes_id,
                record.superseded_by_id,
                record.last_used_at,
                record.success_count,
                record.failure_count,
                record.schema_version,
                int(record.invalidated),
                record.memory_id,
            ),
        )

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
                valid_from, valid_until, supersedes_id, superseded_by_id,
                last_used_at, success_count, failure_count,
                schema_version, invalidated
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                json.dumps(list(record.evidence_refs), ensure_ascii=False),
                record.trust_class,
                record.importance,
                record.writer,
                record.validation_state,
                record.created_at,
                record.updated_at,
                record.valid_from,
                record.valid_until,
                record.supersedes_id,
                record.superseded_by_id,
                record.last_used_at,
                record.success_count,
                record.failure_count,
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
                       valid_from, valid_until, supersedes_id, superseded_by_id,
                       last_used_at, success_count, failure_count,
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
        valid_from=float(row["valid_from"]),
        valid_until=(
            float(row["valid_until"]) if row["valid_until"] is not None else None
        ),
        supersedes_id=(
            str(row["supersedes_id"]) if row["supersedes_id"] is not None else None
        ),
        superseded_by_id=(
            str(row["superseded_by_id"])
            if row["superseded_by_id"] is not None
            else None
        ),
        last_used_at=(
            float(row["last_used_at"]) if row["last_used_at"] is not None else None
        ),
        success_count=int(row["success_count"]),
        failure_count=int(row["failure_count"]),
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
