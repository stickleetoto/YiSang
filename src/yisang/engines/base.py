from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from yisang.memory.models import MemoryProposal

@dataclass
class EngineResult:
    engine_id: str
    text: str
    memory_proposals: list[MemoryProposal] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

class LLMEngine(ABC):
    engine_id: str

    @abstractmethod
    def generate(self, context) -> EngineResult:
        raise NotImplementedError
