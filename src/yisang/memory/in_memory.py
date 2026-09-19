from dataclasses import replace
import time

from .lifecycle import MemoryMutation, new_memory_mutation
from .models import MemoryProposal, MemoryRecord
from .port import MemoryPort


class InMemoryMemoryPort(MemoryPort):
    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []
        self._mutations: list[MemoryMutation] = []

    def search(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        terms = {t.lower() for t in query.split() if t.strip()}
        ranked: list[tuple[float, MemoryRecord]] = []
        for record in self._records:
            if not record.is_active():
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
        selected = [record for _, record in ranked[:limit]]
        self.mark_retrieved([record.memory_id for record in selected])
        return selected

    def commit(self, proposal: MemoryProposal) -> MemoryRecord:
        record = proposal.to_record()
        self._records.append(record)
        self._mutations.append(
            new_memory_mutation(
                memory_id=record.memory_id,
                operation="commit",
                actor=record.writer or record.source,
                reason="governed_commit",
                evidence_refs=record.evidence_refs,
                after=record,
            )
        )
        return record

    def all(self) -> list[MemoryRecord]:
        return list(self._records)

    def mutations(self, memory_id: str | None = None) -> list[MemoryMutation]:
        if memory_id is None:
            return list(self._mutations)
        return [
            mutation
            for mutation in self._mutations
            if mutation.memory_id == memory_id
        ]

    def invalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        index, current = self._locate(memory_id)
        if current.invalidated:
            return current

        updated = replace(
            current,
            invalidated=True,
            validation_state="invalidated",
            updated_at=time.time(),
        )
        self._records[index] = updated
        self._mutations.append(
            new_memory_mutation(
                memory_id=memory_id,
                operation="invalidate",
                actor=actor,
                reason=reason,
                evidence_refs=evidence_refs,
                before=current,
                after=updated,
            )
        )
        return updated

    def revalidate(
        self,
        memory_id: str,
        *,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        index, current = self._locate(memory_id)
        if not current.invalidated:
            return current

        updated = replace(
            current,
            invalidated=False,
            validation_state="committed",
            updated_at=time.time(),
        )
        self._records[index] = updated
        self._mutations.append(
            new_memory_mutation(
                memory_id=memory_id,
                operation="revalidate",
                actor=actor,
                reason=reason,
                evidence_refs=evidence_refs,
                before=current,
                after=updated,
            )
        )
        return updated

    def mark_retrieved(self, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = time.time()
        wanted = set(memory_ids)
        for index, record in enumerate(self._records):
            if record.memory_id in wanted:
                self._records[index] = replace(record, last_used_at=now)

    def record_outcome(self, memory_ids: list[str], *, success: bool) -> None:
        if not memory_ids:
            return
        wanted = set(memory_ids)
        for index, record in enumerate(self._records):
            if record.memory_id not in wanted:
                continue
            self._records[index] = replace(
                record,
                success_count=record.success_count + (1 if success else 0),
                failure_count=record.failure_count + (0 if success else 1),
            )

    def supersede(
        self,
        memory_id: str,
        *,
        superseded_by_id: str,
        actor: str,
        reason: str,
        evidence_refs: tuple[str, ...] = (),
    ) -> MemoryRecord:
        index, current = self._locate(memory_id)
        if current.superseded_by_id == superseded_by_id:
            return current
        now = time.time()
        updated = replace(
            current,
            invalidated=True,
            validation_state="superseded",
            updated_at=now,
            valid_until=now,
            superseded_by_id=superseded_by_id,
        )
        self._records[index] = updated
        self._mutations.append(
            new_memory_mutation(
                memory_id=memory_id,
                operation="supersede",
                actor=actor,
                reason=reason,
                evidence_refs=evidence_refs,
                before=current,
                after=updated,
                metadata={"superseded_by_id": superseded_by_id},
            )
        )
        return updated

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
            self._mutations.append(
                new_memory_mutation(
                    memory_id=record.memory_id,
                    operation="import_overwrite",
                    actor=record.writer or "restore",
                    reason="authoritative_restore",
                    evidence_refs=record.evidence_refs,
                    before=existing,
                    after=record,
                )
            )
            return record
        self._records.append(record)
        self._mutations.append(
            new_memory_mutation(
                memory_id=record.memory_id,
                operation="import",
                actor=record.writer or "restore",
                reason="authoritative_restore",
                evidence_refs=record.evidence_refs,
                after=record,
            )
        )
        return record

    def _locate(self, memory_id: str) -> tuple[int, MemoryRecord]:
        for index, record in enumerate(self._records):
            if record.memory_id == memory_id:
                return index, record
        raise KeyError(f"memory not found: {memory_id}")
