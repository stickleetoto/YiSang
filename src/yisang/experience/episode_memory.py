from __future__ import annotations
from .episode_port import ExperiencePort
from .models import ExperienceEpisode

class InMemoryExperiencePort(ExperiencePort):
    def __init__(self) -> None:
        self._episodes: dict[str, ExperienceEpisode] = {}

    def put_episode(self, episode: ExperienceEpisode) -> None:
        if episode.episode_id in self._episodes:
            raise ValueError(f"duplicate experience episode: {episode.episode_id}")
        self._episodes[episode.episode_id] = episode

    def get_episode(self, episode_id: str) -> ExperienceEpisode | None:
        return self._episodes.get(episode_id)

    def list_episodes(self) -> tuple[ExperienceEpisode, ...]:
        return tuple(self._episodes[key] for key in sorted(self._episodes))
