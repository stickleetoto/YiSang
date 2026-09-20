from __future__ import annotations

from .trace import ActionTrace
from .trace_port import ActionTracePort


class InMemoryActionTracePort(ActionTracePort):
    def __init__(self) -> None:
        self._traces: dict[str, ActionTrace] = {}

    def put_trace(self, trace: ActionTrace) -> None:
        if trace.trace_id in self._traces:
            raise ValueError(f"duplicate action trace: {trace.trace_id}")
        self._traces[trace.trace_id] = trace

    def get_trace(self, trace_id: str) -> ActionTrace | None:
        return self._traces.get(trace_id)

    def for_request(self, request_id: str) -> tuple[ActionTrace, ...]:
        return tuple(
            sorted(
                (
                    trace
                    for trace in self._traces.values()
                    if trace.request_id == request_id
                ),
                key=lambda trace: (trace.ordinal, trace.trace_id),
            )
        )

    def all_traces(self) -> tuple[ActionTrace, ...]:
        return tuple(
            sorted(
                self._traces.values(),
                key=lambda trace: (
                    trace.request_id,
                    trace.ordinal,
                    trace.trace_id,
                ),
            )
        )
