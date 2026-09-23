from __future__ import annotations

import uuid
from typing import Any

from .models import RUN_EVENT_TYPES, RecoveryCheckpoint, RunJournalEvent
from .port import CheckpointPort, RunJournalPort


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
