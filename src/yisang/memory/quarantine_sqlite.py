from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import RLock
from typing import Any
import json
import sqlite3

from .models import MemoryProposal
from .quarantine import QuarantinedMemory, QuarantinePort


class SQLiteQuarantinePort(QuarantinePort):
    """Persistent quarantine store for untrusted memory proposals."""

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
                CREATE TABLE IF NOT EXISTS memory_quarantine (
                    quarantine_id TEXT PRIMARY KEY,
                    proposal_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    risk_flags_json TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    metadata_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_quarantine_created
                ON memory_quarantine(created_at)
                """
            )
            self._conn.commit()

    def put(
        self,
        proposal: MemoryProposal,
        *,
        reason: str,
        risk_flags: tuple[str, ...] = (),
        metadata: dict[str, Any] | None = None,
    ) -> QuarantinedMemory:
        from .quarantine import InMemoryQuarantinePort

        # Reuse the canonical id/timestamp construction from the in-memory store.
        item = InMemoryQuarantinePort().put(
            proposal,
            reason=reason,
            risk_flags=risk_flags,
            metadata=metadata,
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO memory_quarantine (
                    quarantine_id, proposal_json, reason,
                    risk_flags_json, created_at, metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    item.quarantine_id,
                    json.dumps(asdict(proposal), ensure_ascii=False, sort_keys=True),
                    item.reason,
                    json.dumps(list(item.risk_flags), ensure_ascii=False),
                    item.created_at,
                    json.dumps(item.metadata, ensure_ascii=False, sort_keys=True),
                ),
            )
            self._conn.commit()
        return item

    def get(self, quarantine_id: str) -> QuarantinedMemory | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT quarantine_id, proposal_json, reason,
                       risk_flags_json, created_at, metadata_json
                FROM memory_quarantine
                WHERE quarantine_id = ?
                """,
                (quarantine_id,),
            ).fetchone()
        return _row_to_quarantined(row) if row is not None else None

    def all(self) -> list[QuarantinedMemory]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT quarantine_id, proposal_json, reason,
                       risk_flags_json, created_at, metadata_json
                FROM memory_quarantine
                ORDER BY created_at ASC, quarantine_id ASC
                """
            ).fetchall()
        return [_row_to_quarantined(row) for row in rows]

    def remove(self, quarantine_id: str) -> QuarantinedMemory | None:
        item = self.get(quarantine_id)
        if item is None:
            return None
        with self._lock:
            self._conn.execute(
                "DELETE FROM memory_quarantine WHERE quarantine_id = ?",
                (quarantine_id,),
            )
            self._conn.commit()
        return item

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def __enter__(self) -> "SQLiteQuarantinePort":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()


def _row_to_quarantined(row: sqlite3.Row) -> QuarantinedMemory:
    proposal_raw = _decode_json_object(row["proposal_json"])
    risk_flags_raw = _decode_json_list(row["risk_flags_json"])
    metadata = _decode_json_object(row["metadata_json"])

    proposal = MemoryProposal(
        content=str(proposal_raw["content"]),
        kind=str(proposal_raw.get("kind", "semantic")),
        source_engine=str(proposal_raw.get("source_engine", "unknown")),
        confidence=float(proposal_raw.get("confidence", 0.5)),
        evidence=[
            str(item)
            for item in proposal_raw.get("evidence", [])
            if isinstance(item, (str, int, float, bool))
        ],
        metadata=(
            dict(proposal_raw.get("metadata", {}))
            if isinstance(proposal_raw.get("metadata"), dict)
            else {}
        ),
        source_id=(
            str(proposal_raw["source_id"])
            if proposal_raw.get("source_id") is not None
            else None
        ),
        source_type=str(proposal_raw.get("source_type", "engine")),
        trust_class=str(proposal_raw.get("trust_class", "unknown")),
        importance=float(proposal_raw.get("importance", 0.5)),
        writer=(
            str(proposal_raw["writer"])
            if proposal_raw.get("writer") is not None
            else None
        ),
        valid_from=(
            float(proposal_raw["valid_from"])
            if proposal_raw.get("valid_from") is not None
            else None
        ),
        valid_until=(
            float(proposal_raw["valid_until"])
            if proposal_raw.get("valid_until") is not None
            else None
        ),
        supersedes_id=(
            str(proposal_raw["supersedes_id"])
            if proposal_raw.get("supersedes_id") is not None
            else None
        ),
    )

    return QuarantinedMemory(
        quarantine_id=str(row["quarantine_id"]),
        proposal=proposal,
        reason=str(row["reason"]),
        risk_flags=tuple(risk_flags_raw),
        created_at=float(row["created_at"]),
        metadata=metadata,
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
