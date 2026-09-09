from abc import ABC, abstractmethod
from .models import MemoryRecord, MemoryProposal

class MemoryPort(ABC):
    @abstractmethod
    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        raise NotImplementedError

    @abstractmethod
    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        raise NotImplementedError

    @abstractmethod
    def all(self) -> list[MemoryRecord]:
        raise NotImplementedError
