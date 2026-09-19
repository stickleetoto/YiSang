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

    def import_record(
        self,
        record: MemoryRecord,
        *,
        overwrite: bool = False,
    ) -> MemoryRecord:
        """Import an authoritative record without re-proposing it.

        This path is reserved for verified restore/migration operations. Normal
        model/session writes must continue through MemoryProposal + governance.
        """
        raise NotImplementedError("memory backend does not support record import")
