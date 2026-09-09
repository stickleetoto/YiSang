from dataclasses import dataclass, field

@dataclass(frozen=True)
class EgoManifest:
    ego_id: str
    name: str
    provides: tuple[str, ...]
    keywords: tuple[str, ...] = ()
    instructions: str = ""
    permissions: dict[str, str | bool] = field(default_factory=dict)
