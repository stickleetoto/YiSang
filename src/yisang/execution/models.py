from dataclasses import dataclass, field
from typing import Any

@dataclass
class ActionProposal:
    action: str
    arguments: dict[str, Any] = field(default_factory=dict)
