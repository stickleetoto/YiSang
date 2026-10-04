from __future__ import annotations

from abc import ABC, abstractmethod

from .models import ExperienceCandidate


class ExperiencePort(ABC):
    """Authoritative store for pre-promotion experience candidates."""

    @abstractmethod
    def get(self, candidate_key: str) -> ExperienceCandidate | None:
        raise NotImplementedError

    @abstractmethod
    def put(self, candidate: ExperienceCandidate) -> None:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> tuple[ExperienceCandidate, ...]:
        raise NotImplementedError
