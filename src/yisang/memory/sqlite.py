from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from .port import MemoryPort
from .models import MemoryRecord, MemoryProposal

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]+")

def _terms(text: str) -> set[str]:
    return {m.group(0).lower() for m in _TOKEN_RE.finditer(text)}

class SQLiteMemoryPort(MemoryPort):
    """Small standalone persistent memory backend.

    This is intentionally simple. BIO can later implement the same MemoryPort
    contract without changing YiSang Core.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS memories (
                memory_id TEXT PRIMARY KEY,
                kind TEXT NOT NULL,
                content TEXT NOT NULL,
                source TEXT NOT NULL,
                confidence REAL NOT NULL,
                metadata_json TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        query_terms = _terms(query)
        if not query_terms:
            return []

        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self.all():
            record_terms = _terms(record.content)
            overlap = len(query_terms & record_terms)
            if overlap == 0:
                continue
            score = float(overlap) + max(0.0, min(1.0, record.confidence)) * 0.10
            ranked.append((score, record))

        ranked.sort(key=lambda item: (-item[0], item[1].memory_id))
        return [record for _, record in ranked[:limit]]

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = proposal.to_record()
        self._conn.execute(
            """
            INSERT INTO memories (
                memory_id, kind, content, source, confidence, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                record.memory_id,
                record.kind,
                record.content,
                record.source,
                record.confidence,
                json.dumps(record.metadata, ensure_ascii=False, sort_keys=True),
            ),
        )
        self._conn.commit()
        return record

    def all(self) -> list[MemoryRecord]:
        rows = self._conn.execute(
            """
            SELECT memory_id, kind, content, source, confidence, metadata_json
            FROM memories
            ORDER BY rowid ASC
            """
        ).fetchall()

        return [
            MemoryRecord(
                memory_id=row["memory_id"],
                kind=row["kind"],
                content=row["content"],
                source=row["source"],
                confidence=float(row["confidence"]),
                metadata=json.loads(row["metadata_json"]),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "SQLiteMemoryPort":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
