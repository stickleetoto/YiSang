from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .models import RecoveryCheckpoint, RunJournalEvent, SideEffectReceipt


class RunJournalPort(ABC):
    @abstractmethod
    def append(
        self,
        goal_id: str,
        run_id: str,
        event_type: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> RunJournalEvent:
        raise NotImplementedError

    @abstractmethod
    def events(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
        after_sequence: int = 0,
    ) -> tuple[RunJournalEvent, ...]:
        raise NotImplementedError

    @abstractmethod
    def latest_sequence(self, goal_id: str, run_id: str) -> int:
        raise NotImplementedError


class CheckpointPort(ABC):
    @abstractmethod
    def put(self, checkpoint: RecoveryCheckpoint) -> None:
        raise NotImplementedError

    @abstractmethod
    def latest(
        self,
        goal_id: str,
        *,
        run_id: str | None = None,
    ) -> RecoveryCheckpoint | None:
        raise NotImplementedError

    @abstractmethod
    def list_all(
        self,
        goal_id: str,
    ) -> tuple[RecoveryCheckpoint, ...]:
        raise NotImplementedError



class SideEffectReceiptPort(ABC):
    @abstractmethod
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
        raise NotImplementedError

    @abstractmethod
    def get_receipt(
        self,
        goal_id: str,
        idempotency_key: str,
    ) -> SideEffectReceipt | None:
        raise NotImplementedError

    @abstractmethod
    def commit_receipt(
        self,
        receipt_id: str,
        *,
        result_ref: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        raise NotImplementedError

    @abstractmethod
    def fail_receipt(
        self,
        receipt_id: str,
        *,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> SideEffectReceipt:
        raise NotImplementedError

    @abstractmethod
    def retry_receipt(
        self,
        receipt_id: str,
        *,
        run_id: str,
        reason: str,
    ) -> SideEffectReceipt:
        raise NotImplementedError

    @abstractmethod
    def receipts(
        self,
        goal_id: str,
    ) -> tuple[SideEffectReceipt, ...]:
        raise NotImplementedError
