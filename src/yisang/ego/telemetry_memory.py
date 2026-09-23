from __future__ import annotations

from .telemetry import EgoTelemetryEvent, EgoTelemetryPort


class InMemoryEgoTelemetryPort(EgoTelemetryPort):
    def __init__(self) -> None:
        self._events: dict[str, EgoTelemetryEvent] = {}

    def record(self, event: EgoTelemetryEvent) -> EgoTelemetryEvent:
        existing = self._events.get(event.event_id)
        if existing is not None:
            if existing != event:
                raise ValueError(
                    f"conflicting E.G.O telemetry event: {event.event_id}"
                )
            return existing
        self._events[event.event_id] = event
        return event

    def events(
        self,
        *,
        ego_id: str | None = None,
        version: str | None = None,
    ) -> tuple[EgoTelemetryEvent, ...]:
        items = (
            item
            for item in self._events.values()
            if (ego_id is None or item.ego_id == ego_id)
            and (version is None or item.version == version)
        )
        return tuple(
            sorted(items, key=lambda item: (item.created_at, item.event_id))
        )
