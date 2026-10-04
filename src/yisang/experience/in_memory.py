from __future__ import annotations

from .models import ExperienceCandidate
from .port import ExperiencePort


class InMemoryExperiencePort(ExperiencePort):
    def __init__(self) -> None:
        self._items: dict[str, ExperienceCandidate] = {}

    def get(self, candidate_key: str) -> ExperienceCandidate | None:
        return self._items.get(candidate_key)

    def put(self, candidate: ExperienceCandidate) -> None:
        self._items[candidate.candidate_key] = candidate

    def all(self) -> tuple[ExperienceCandidate, ...]:
        return tuple(
            self._items[key]
            for key in sorted(self._items)
        )
