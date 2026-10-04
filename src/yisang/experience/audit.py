from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import json
from pathlib import Path
import sqlite3
from threading import RLock
import time
from typing import Any
import uuid

PROMOTION_MUTATION_OPERATIONS = frozenset(
    {"promote", "reinforce", "revoke"}
)


@dataclass(frozen=True)
class PromotionMutation:
    mutation_id: str
    candidate_key: str
    target_book_id: str
    target_entry_id: str
    operation: str
    actor: str
    reason: str
    before_note: dict[str, Any] | None
    after_note: dict[str, Any] | None
    evidence_ids: tuple[str, ...] = ()
    verification_refs: tuple[str, ...] = ()
    source_episode_ids: tuple[str, ...] = ()
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.mutation_id.strip():
            raise ValueError("mutation_id must be non-empty")
        if not self.candidate_key.strip():
            raise ValueError("candidate_key must be non-empty")
        if not self.target_book_id.strip():
            raise ValueError("target_book_id must be non-empty")
        if not self.target_entry_id.strip():
            raise ValueError("target_entry_id must be non-empty")
        if self.operation not in PROMOTION_MUTATION_OPERATIONS:
            raise ValueError(
                f"unsupported promotion mutation: {self.operation}"
            )
        if not self.actor.strip():
            raise ValueError("actor must be non-empty")
        if not self.reason.strip():
            raise ValueError("reason must be non-empty")

    def to_dict(self) -> dict[str, Any]:
        return {
            "mutation_id": self.mutation_id,
            "candidate_key": self.candidate_key,
            "target_book_id": self.target_book_id,
            "target_entry_id": self.target_entry_id,
            "operation": self.operation,
            "actor": self.actor,
            "reason": self.reason,
            "before_note": (
                dict(self.before_note)
                if self.before_note is not None
                else None
            ),
            "after_note": (
                dict(self.after_note)
                if self.after_note is not None
                else None
            ),
            "evidence_ids": list(self.evidence_ids),
            "verification_refs": list(self.verification_refs),
            "source_episode_ids": list(self.source_episode_ids),
            "created_at": self.created_at,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PromotionMutation":
        before = data.get("before_note")
        after = data.get("after_note")
        return cls(
            mutation_id=str(data["mutation_id"]),
            candidate_key=str(data["candidate_key"]),
            target_book_id=str(data["target_book_id"]),
            target_entry_id=str(data["target_entry_id"]),
            operation=str(data["operation"]),
            actor=str(data["actor"]),
            reason=str(data["reason"]),
            before_note=dict(before) if isinstance(before, dict) else None,
            after_note=dict(after) if isinstance(after, dict) else None,
            evidence_ids=tuple(
                str(item) for item in data.get("evidence_ids", ())
            ),
            verification_refs=tuple(
                str(item) for item in data.get("verification_refs", ())
            ),
            source_episode_ids=tuple(
                str(item) for item in data.get("source_episode_ids", ())
            ),
            created_at=float(data.get("created_at", 0.0)),
            metadata=dict(data.get("metadata", {})),
        )


@dataclass(frozen=True)
class PromotionRevokeResult:
    status: str
    reason: str
    candidate_key: str
    mutation: PromotionMutation | None = None


class PromotionAuditPort(ABC):
    @abstractmethod
    def append(self, mutation: PromotionMutation) -> None:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> tuple[PromotionMutation, ...]:
        raise NotImplementedError

    def for_candidate(
        self,
        candidate_key: str,
    ) -> tuple[PromotionMutation, ...]:
        return tuple(
            item
            for item in self.all()
            if item.candidate_key == candidate_key
        )


class InMemoryPromotionAuditPort(PromotionAuditPort):
    def __init__(self) -> None:
        self._items: list[PromotionMutation] = []

    def append(self, mutation: PromotionMutation) -> None:
        if any(
            item.mutation_id == mutation.mutation_id
            for item in self._items
        ):
            raise ValueError(
                f"promotion mutation already exists: "
                f"{mutation.mutation_id}"
            )
        self._items.append(mutation)

    def all(self) -> tuple[PromotionMutation, ...]:
        return tuple(self._items)


class SQLitePromotionAuditPort(PromotionAuditPort):
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experience_promotion_mutations (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    mutation_id TEXT NOT NULL UNIQUE,
                    candidate_key TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            self._conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                idx_experience_promotion_candidate
                ON experience_promotion_mutations(
                    candidate_key, sequence
                )
                """
            )
            self._conn.commit()

    def append(self, mutation: PromotionMutation) -> None:
        payload = json.dumps(
            mutation.to_dict(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO experience_promotion_mutations(
                    mutation_id,
                    candidate_key,
                    created_at,
                    payload_json
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    mutation.mutation_id,
                    mutation.candidate_key,
                    mutation.created_at,
                    payload,
                ),
            )
            self._conn.commit()

    def all(self) -> tuple[PromotionMutation, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json
                FROM experience_promotion_mutations
                ORDER BY sequence ASC
                """
            ).fetchall()
        return tuple(
            PromotionMutation.from_dict(
                json.loads(str(row["payload_json"]))
            )
            for row in rows
        )

    def for_candidate(
        self,
        candidate_key: str,
    ) -> tuple[PromotionMutation, ...]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT payload_json
                FROM experience_promotion_mutations
                WHERE candidate_key = ?
                ORDER BY sequence ASC
                """,
                (candidate_key,),
            ).fetchall()
        return tuple(
            PromotionMutation.from_dict(
                json.loads(str(row["payload_json"]))
            )
            for row in rows
        )


def new_promotion_mutation(
    *,
    candidate_key: str,
    target_book_id: str,
    target_entry_id: str,
    operation: str,
    actor: str,
    reason: str,
    before_note: dict[str, Any] | None,
    after_note: dict[str, Any] | None,
    evidence_ids: tuple[str, ...] = (),
    verification_refs: tuple[str, ...] = (),
    source_episode_ids: tuple[str, ...] = (),
    metadata: dict[str, Any] | None = None,
) -> PromotionMutation:
    return PromotionMutation(
        mutation_id=f"pmut-{uuid.uuid4().hex[:12]}",
        candidate_key=candidate_key,
        target_book_id=target_book_id,
        target_entry_id=target_entry_id,
        operation=operation,
        actor=actor,
        reason=reason,
        before_note=(
            dict(before_note) if before_note is not None else None
        ),
        after_note=(
            dict(after_note) if after_note is not None else None
        ),
        evidence_ids=tuple(evidence_ids),
        verification_refs=tuple(verification_refs),
        source_episode_ids=tuple(source_episode_ids),
        metadata=dict(metadata or {}),
    )
