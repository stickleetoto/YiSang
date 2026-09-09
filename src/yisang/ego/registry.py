from .models import EgoManifest

class EgoRegistry:
    def __init__(self) -> None:
        self._egos: dict[str, EgoManifest] = {}

    def register(self, ego: EgoManifest) -> None:
        if ego.ego_id in self._egos:
            raise ValueError(f"duplicate E.G.O id: {ego.ego_id}")
        self._egos[ego.ego_id] = ego

    def get(self, ego_id: str) -> EgoManifest:
        return self._egos[ego_id]

    def list_all(self) -> list[EgoManifest]:
        return list(self._egos.values())
