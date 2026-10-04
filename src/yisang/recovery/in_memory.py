from __future__ import annotations

from dataclasses import replace
import time
import uuid
from typing import Any

from .models import (
    RUN_EVENT_TYPES,
    RecoveryCheckpoint,
    RunJournalEvent,
    SideEffectReceipt,
)
from .port import CheckpointPort, RunJournalPort, SideEffectReceiptPort


class InMemoryRunJournalPort(RunJournalPort):
    def __init__(self) -> None:
        self._events: list[RunJournalEvent] = []

    def append(
        self,
        goal_id: str,
        run_id: str,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> RunJournalEvent:
        if event_type not in RUN_EVENT_TYPES:
            raise ValueError(f"unsupported run journal event: {event_type}")
        sequence = self.latest_sequence(goal_id, run_id) + 1
        event = RunJournalEvent(
            event_id=f"run-event-{uuid.uuid4().hex[:16]}",
            goal_id=goal_id,
            run_id=run_id,
            sequence=sequence,
            event_type=event_type,
            payload=dict(payload or {}),
        )
        self._events.append(event)
        return event

    def events(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
        after_sequence: int = 0,
    ) -> tuple[RunJournalEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must be non-negative")
        return tuple(
            event
            for event in self._events
            if event.goal_id == goal_id
            and (run_id is None or event.run_id == run_id)
            and event.sequence > after_sequence
        )

    def latest_sequence(self, goal_id: str, run_id: str) -> int:
        sequences = [
            event.sequence
            for event in self._events
            if event.goal_id == goal_id and event.run_id == run_id
        ]
        return max(sequences, default=0)


class InMemoryCheckpointPort(CheckpointPort):
    def __init__(self) -> None:
        self._items: dict[str, RecoveryCheckpoint] = {}

    def put(self, checkpoint: RecoveryCheckpoint) -> None:
        if checkpoint.checkpoint_id in self._items:
            raise ValueError(
                f"duplicate checkpoint: {checkpoint.checkpoint_id}"
            )
        self._items[checkpoint.checkpoint_id] = checkpoint

    def latest(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> RecoveryCheckpoint | None:
        items = [
            item
            for item in self._items.values()
            if item.goal_id == goal_id
            and (run_id is None or item.run_id == run_id)
        ]
        if not items:
            return None
        if run_id is None:
            return max(
                items,
                key=lambda item: (
                    item.created_at,
                    item.journal_sequence,
                    item.checkpoint_id,
                ),
            )
        return max(
            items,
            key=lambda item: (
                item.journal_sequence,
                item.created_at,
                item.checkpoint_id,
            ),
        )

    def list_all(
        self,
        goal_id: str,
    ) -> tuple[RecoveryCheckpoint, ...]:
        return tuple(
            sorted(
                (
                    item for item in self._items.values()
                    if item.goal_id == goal_id
                ),
                key=lambda item: (
                    item.created_at,
                    item.journal_sequence,
                    item.checkpoint_id,
                ),
            )
        )



class InMemorySideEffectReceiptPort(SideEffectReceiptPort):
    def __init__(self) -> None:
        self._items: dict[str, SideEffectReceipt] = {}
        self._by_key: dict[tuple[str, str], str] = {}

    def reserve(
        self,
        *,
        goal_id: str,
        run_id: str,
        idempotency_key: str,
        tool_id: str,
        request_digest: str,
        metadata: dict[str, Any] | None = None,
    ) -> SideEffectReceipt:
        key = (goal_id, idempotency_key)
        existing_id = self._by_key.get(key)
        if existing_id is not None:
            existing = self._items[existing_id]
            if (
                existing.request_digest != request_digest
                or existing.tool_id != tool_id
            ):
                raise ValueError(
                    "idempotency key reused for different side effect"
                )
            return existing
        receipt = SideEffectReceipt(
            receipt_id=f"side-effect-{uuid.uuid4().hex[:16]}",
            goal_id=goal_id,
            run_id=run_id,
            idempotency_key=idempotency_key,
            tool_id=tool_id,
            request_digest=request_digest,
            metadata=dict(metadata or {}),
        )
        self._items[receipt.receipt_id] = receipt
        self._by_key[key] = receipt.receipt_id
        return receipt

    def get_receipt(
        self,
        goal_id: str,
        idempotency_key: str,
    ) -> SideEffectReceipt | None:
        receipt_id = self._by_key.get((goal_id, idempotency_key))
        return None if receipt_id is None else self._items[receipt_id]

    def commit_receipt(
        self,
        receipt_id: str,
        *,
        result_ref: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        current = self._required(receipt_id)
        if current.state == "committed":
            return current
        if current.state == "failed":
            raise ValueError("failed receipt cannot become committed")
        value = result_ref.strip()
        if not value:
            raise ValueError("result_ref must be non-empty")
        updated = replace(
            current,
            state="committed",
            result_ref=value,
            evidence_refs=tuple(evidence_refs),
            updated_at=time.time(),
        )
        self._items[receipt_id] = updated
        return updated

    def fail_receipt(
        self,
        receipt_id: str,
        *,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        current = self._required(receipt_id)
        if current.state == "committed":
            raise ValueError("committed receipt cannot become failed")
        value = reason.strip()
        if not value:
            raise ValueError("reason must be non-empty")
        if current.state == "failed":
            return current
        updated = replace(
            current,
            state="failed",
            failure_reason=value,
            evidence_refs=tuple(evidence_refs),
            updated_at=time.time(),
        )
        self._items[receipt_id] = updated
        return updated

    def retry_receipt(
        self,
        receipt_id: str,
        *,
        run_id: str,
        reason: str,
    ) -> SideEffectReceipt:
        current = self._required(receipt_id)
        if current.state != "failed":
            raise ValueError("only failed receipts may be retried")
        normalized_run = run_id.strip()
        normalized_reason = reason.strip()
        if not normalized_run:
            raise ValueError("run_id must be non-empty")
        if not normalized_reason:
            raise ValueError("reason must be non-empty")
        updated = replace(
            current,
            run_id=normalized_run,
            state="started",
            result_ref=None,
            evidence_refs=(),
            failure_reason=None,
            attempt_count=current.attempt_count + 1,
            last_retry_reason=normalized_reason,
            updated_at=time.time(),
        )
        self._items[receipt_id] = updated
        return updated

    def receipts(
        self,
        goal_id: str,
    ) -> tuple[SideEffectReceipt, ...]:
        return tuple(
            sorted(
                (
                    item for item in self._items.values()
                    if item.goal_id == goal_id
                ),
                key=lambda item: (item.created_at, item.receipt_id),
            )
        )

    def _required(self, receipt_id: str) -> SideEffectReceipt:
        try:
            return self._items[receipt_id]
        except KeyError as exc:
            raise KeyError(receipt_id) from exc
