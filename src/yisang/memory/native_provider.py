from __future__ import annotations

from .models import MemoryProposal, MemoryRecord
from .pipeline import MemoryWritePipeline, MemoryWriteStatus
from .port import MemoryPort
from .provider import (
    MemoryProvider,
    ProviderContext,
    ProviderCurrentState,
    ProviderWriteResult,
)


class NativeMemoryProvider(MemoryProvider):
    provider_id = "native"

    def __init__(
        self,
        *,
        memory: MemoryPort,
        pipeline: MemoryWritePipeline,
    ) -> None:
        if pipeline.memory is not memory:
            raise ValueError("pipeline must be backed by the same MemoryPort")
        self.memory = memory
        self.pipeline = pipeline

    def recall(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        return self.memory.search(query, limit=limit)

    def remember(self, proposal: MemoryProposal) -> ProviderWriteResult:
        result = self.pipeline.submit(proposal)
        status_map = {
            MemoryWriteStatus.COMMITTED: "committed",
            MemoryWriteStatus.QUARANTINED: "quarantined",
            MemoryWriteStatus.REJECTED: "rejected",
        }
        return ProviderWriteResult(
            provider_id=self.provider_id,
            status=status_map[result.status],
            record=result.record,
            proposal_ref=(
                f"native-quarantine:{result.quarantine.quarantine_id}"
                if result.quarantine is not None
                else None
            ),
            reason=result.reason,
            warnings=tuple(result.risk_flags),
        )

    def get_current_state(self, topic_key: str) -> ProviderCurrentState:
        results = self.recall(topic_key, limit=1)
        current = results[0] if results else None
        return ProviderCurrentState(
            provider_id=self.provider_id,
            topic_key=topic_key,
            current_memory_id=current.memory_id if current is not None else None,
            confidence=current.confidence if current is not None else 0.0,
            reasoning=(
                "selected top active native recall result"
                if current is not None
                else "no active native memory matched"
            ),
            candidates=(
                (
                    {
                        "memory_id": current.memory_id,
                        "content": current.content,
                        "confidence": current.confidence,
                    },
                )
                if current is not None
                else ()
            ),
            metadata={"strategy": "active_recall_top1"},
        )

    def get_context(
        self,
        query: str,
        *,
        limit: int = 8,
        char_budget: int = 2400,
    ) -> ProviderContext:
        if char_budget <= 0:
            raise ValueError("char_budget must be positive")
        memories = tuple(self.recall(query, limit=limit))
        chunks: list[str] = []
        used = 0
        included: list[MemoryRecord] = []
        for memory in memories:
            chunk = f"[{memory.memory_id}] {memory.content}".strip()
            separator = 1 if chunks else 0
            remaining = char_budget - used - separator
            if remaining <= 0:
                break
            bounded = chunk[:remaining]
            chunks.append(bounded)
            used += len(bounded) + separator
            included.append(memory)
            if len(bounded) < len(chunk):
                break
        return ProviderContext(
            provider_id=self.provider_id,
            text="\n".join(chunks),
            memories=tuple(included),
            metadata={
                "strategy": "native_compact_context",
                "char_budget": char_budget,
                "context_chars": min(used, char_budget),
            },
        )
