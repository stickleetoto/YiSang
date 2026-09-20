from __future__ import annotations

from abc import ABC, abstractmethod

from .trace import ActionTrace


class ActionTracePort(ABC):
    @abstractmethod
    def put_trace(self, trace: ActionTrace) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_trace(self, trace_id: str) -> ActionTrace | None:
        raise NotImplementedError

    @abstractmethod
    def for_request(self, request_id: str) -> tuple[ActionTrace, ...]:
        raise NotImplementedError

    @abstractmethod
    def all_traces(self) -> tuple[ActionTrace, ...]:
        raise NotImplementedError
