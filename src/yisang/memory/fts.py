from __future__ import annotations

from pathlib import Path
import re
import sqlite3
from threading import RLock

from .models import MemoryRecord
from .projection import MemoryHit, MemoryProjection

_TOKEN_RE = re.compile(r"[A-Za-z0-9_가-힣]+")


class SQLiteFTSProjection(MemoryProjection):
    """Rebuildable SQLite FTS5/BM25 projection.

    The projection owns only searchable copies of authoritative records. Deleting
    this database must never delete YiSang's authoritative memory.
    """

    projection_id = "sqlite-fts5-bm25-v1"

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock:
            try:
                self._conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                    USING fts5(
                        memory_id UNINDEXED,
                        content,
                        kind UNINDEXED,
                        trust_class UNINDEXED,
                        tokenize='unicode61'
                    )
                    """
                )
            except sqlite3.OperationalError as exc:
                raise RuntimeError(
                    "SQLite FTS5 is required for SQLiteFTSProjection"
                ) from exc
            self._conn.commit()

    def rebuild(self, records: list[MemoryRecord]) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM memory_fts")
            for record in records:
                if record.invalidated or not record.is_durable:
                    continue
                self._insert(record)
            self._conn.commit()

    def upsert(self, record: MemoryRecord) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?",
                (record.memory_id,),
            )
            if not record.invalidated and record.is_durable:
                self._insert(record)
            self._conn.commit()

    def remove(self, memory_id: str) -> None:
        with self._lock:
            self._conn.execute(
                "DELETE FROM memory_fts WHERE memory_id = ?",
                (memory_id,),
            )
            self._conn.commit()

    def search(self, query: str, *, limit: int = 8) -> list[MemoryHit]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        if limit == 0:
            return []

        fts_query = _fts_query(query)
        if not fts_query:
            return []

        with self._lock:
            rows = self._conn.execute(
                """
                SELECT memory_id, bm25(memory_fts) AS rank_score
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank_score ASC, memory_id ASC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

        # Projection scores are local-only. Cross-projection fusion uses rank,
        # not the raw BM25 number, because score scales differ by index type.
        return [
            MemoryHit(
                memory_id=str(row["memory_id"]),
                score=1.0 / rank,
                projection=self.projection_id,
            )
            for rank, row in enumerate(rows, start=1)
        ]

    def size(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS count FROM memory_fts"
            ).fetchone()
        return int(row["count"])

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteFTSProjection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def _insert(self, record: MemoryRecord) -> None:
        self._conn.execute(
            """
            INSERT INTO memory_fts(memory_id, content, kind, trust_class)
            VALUES (?, ?, ?, ?)
            """,
            (
                record.memory_id,
                record.content,
                record.kind,
                record.trust_class,
            ),
        )


def _fts_query(query: str) -> str:
    terms = [
        match.group(0).lower()
        for match in _TOKEN_RE.finditer(query)
    ]
    if not terms:
        return ""
    escaped = [term.replace('"', '""') for term in terms]
    return " OR ".join(f'"{term}"' for term in escaped)
