from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from threading import RLock

from .models import ExperienceCandidate
from .port import ExperiencePort


class SQLiteExperiencePort(ExperiencePort):
    """Durable store for pre-promotion experience candidates."""

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
                CREATE TABLE IF NOT EXISTS experience_candidates (
                    candidate_key TEXT PRIMARY KEY,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.commit()

    def get(self, candidate_key: str) -> ExperienceCandidate | None:
        with self._lock:
            row = self._conn.execute(
                """
                SELECT payload_json
                FROM experience_candidates
                WHERE candidate_key = ?
                """,
                (candidate_key,),
            ).fetchone()
        if row is None:
            return None
        return ExperienceCandidate.from_dict(
            json.loads(str(row["payload_json"]))
        )

    def put(self, candidate: ExperienceCandidate) -> None:
        payload = json.dumps(
            candidate.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO experience_candidates(candidate_key, payload_json)
                VALUES (?, ?)
                ON CONFLICT(candidate_key)
                DO UPDATE SET payload_json = excluded.payload_json
                """,
                (candidate.candidate_key, payload),
            )
            self._conn.commit()

    def all(self) -> tuple[ExperienceCandidate, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json
                FROM experience_candidates
                ORDER BY candidate_key ASC
                """
            ).fetchall()
        return tuple(
            ExperienceCandidate.from_dict(
                json.loads(str(row["payload_json"]))
            )
            for row in rows
        )
