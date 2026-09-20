from __future__ import annotations
from abc import ABC, abstractmethod
from .models import ExperienceEpisode

class ExperiencePort(ABC):
    """Authoritative storage boundary for normalized runtime episodes."""

    @abstractmethod
    def put_episode(self, episode: ExperienceEpisode) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_episode(self, episode_id: str) -> ExperienceEpisode | None:
        raise NotImplementedError

    @abstractmethod
    def list_episodes(self) -> tuple[ExperienceEpisode, ...]:
        raise NotImplementedError
