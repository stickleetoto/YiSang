from .models import MemoryProposal, MemoryRecord
from .port import MemoryPort


class InMemoryMemoryPort(MemoryPort):
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        terms = {t.lower() for t in query.split() if t.strip()}
        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self._records:
            if record.invalidated:
                continue
            hay = record.content.lower()
            overlap = sum(1 for term in terms if term in hay)
            if not overlap:
                continue
            score = (
                float(overlap)
                + max(0.0, min(1.0, record.confidence)) * 0.10
                + max(0.0, min(1.0, record.importance)) * 0.05
            )
            ranked.append((score, record))
        ranked.sort(key=lambda item: (-item[0], item[1].memory_id))
        return [record for _, record in ranked[:limit]]

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = proposal.to_record()
        self._records.append(record)
        return record

    def all(self) -> list[MemoryRecord]:
        return list(self._records)

    def import_record(
        self,
        record: MemoryRecord,
        *,
        overwrite: bool = False,
    ) -> MemoryRecord:
        for index, existing in enumerate(self._records):
            if existing.memory_id != record.memory_id:
                continue
            if not overwrite:
                raise ValueError(f"memory already exists: {record.memory_id}")
            self._records[index] = record
            return record
        self._records.append(record)
        return record
