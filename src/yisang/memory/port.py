from abc import ABC, abstractmethod
from .lifecycle import MemoryMutation
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

    def get(self, memory_id: str) -> MemoryRecord | None:
        for record in self.all():
            if record.memory_id == memory_id:
                return record
        return None

    def mutations(self, memory_id: str | None = None) -> list[MemoryMutation]:
        raise NotImplementedError("memory backend does not support mutation history")

    def invalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        raise NotImplementedError("memory backend does not support invalidation")

    def revalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        raise NotImplementedError("memory backend does not support revalidation")

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
