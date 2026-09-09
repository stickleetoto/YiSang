from .port import MemoryPort
from .models import MemoryRecord, MemoryProposal

class InMemoryMemoryPort(MemoryPort):
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        terms = {t.lower() for t in query.split() if t.strip()}
        ranked = []
        for record in self._records:
            hay = record.content.lower()
            score = sum(1 for t in terms if t in hay)
            if score:
                ranked.append((score, record))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [r for _, r in ranked[:limit]]

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = proposal.to_record()
        self._records.append(record)
        return record

    def all(self) -> list[MemoryRecord]:
        return list(self._records)
