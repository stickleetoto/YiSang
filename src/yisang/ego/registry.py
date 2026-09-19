from pathlib import Path

from .models import EgoManifest
from .loader import load_ego_directory

class EgoRegistry:
    def __init__(self) -> None:
        self._egos: dict[str, EgoManifest] = {}

    def register(self, ego: EgoManifest) -> None:
        if ego.ego_id in self._egos:
            raise ValueError(f"duplicate E.G.O id: {ego.ego_id}")
        self._egos[ego.ego_id] = ego

    def load_directory(self, root: str | Path) -> int:
        count = 0
        for ego in load_ego_directory(root):
            self.register(ego)
            count += 1
        return count

    @classmethod
    def from_directory(cls, root: str | Path) -> "EgoRegistry":
        registry = cls()
        registry.load_directory(root)
        return registry

    def get(self, ego_id: str) -> EgoManifest:
        return self._egos[ego_id]

    def list_all(self) -> list[EgoManifest]:
        return list(self._egos.values())
