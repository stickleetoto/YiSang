from __future__ import annotations

from dataclasses import dataclass


SCENARIO_KINDS = frozenset({"resume", "stale", "correction"})


@dataclass(frozen=True)
class MemoryValidationScenario:
    scenario_id: str
    kind: str
    query: str
    required_substrings: tuple[str, ...] = ()
    forbidden_substrings: tuple[str, ...] = ()
    topic_key: str | None = None

    def __post_init__(self) -> None:
        if not self.scenario_id.strip():
            raise ValueError("scenario_id must be non-empty")
        if self.kind not in SCENARIO_KINDS:
            raise ValueError(f"unsupported scenario kind: {self.kind}")
        if not self.query.strip():
            raise ValueError("query must be non-empty")
