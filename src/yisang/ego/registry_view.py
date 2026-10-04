from __future__ import annotations

from .port import EgoPort


class DurableEgoRegistryView:
    """Read-only registry view exposing only active durable E.G.O packages."""

    def __init__(self, port: EgoPort) -> None:
        self.port = port

    def get(self, ego_id: str):
        item = self.port.get(ego_id)
        if item is None or not item.active:
            raise KeyError(ego_id)
        return item.manifest

    def list_all(self):
        return [item.manifest for item in self.port.list_active()]
