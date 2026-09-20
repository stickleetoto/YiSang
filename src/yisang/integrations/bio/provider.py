from __future__ import annotations

from typing import Any

from yisang.memory.models import MemoryProposal, MemoryRecord
from yisang.memory.provider import (
    MemoryProvider,
    ProviderContext,
    ProviderCurrentState,
    ProviderWriteResult,
)

from .client import BioMemoryClient
from .config import BioProviderConfig
from .mapper import map_context_memories, map_search_payload


_KIND_TO_BIO_TYPE = {
    "semantic": "project",
    "episodic": "log",
    "procedural": "success",
    "working": "log",
}


class BioMemoryProvider(MemoryProvider):
    provider_id = "bio"

    def __init__(
        self,
        *,
        client: BioMemoryClient,
        config: BioProviderConfig | None = None,
    ) -> None:
        self.client = client
        self.config = config or BioProviderConfig()

    def recall(self, query: str, *, limit: int = 8) -> list[MemoryRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        payload = self.client.search(
            query,
            project=self.config.project,
            namespace=self.config.namespace,
            limit=limit,
        )
        return [record for record in map_search_payload(payload) if record.is_active()]

    def remember(self, proposal: MemoryProposal) -> ProviderWriteResult:
        memory_type = str(
            proposal.metadata.get("bio_memory_type")
            or _KIND_TO_BIO_TYPE.get(proposal.kind, "project")
        )
        title = _proposal_title(proposal)
        payload = self.client.propose(
            project=self.config.project,
            namespace=self.config.namespace,
            memory_type=memory_type,
            title=title,
            content=proposal.content,
            tags=_string_list(proposal.metadata.get("tags")),
            importance=max(1, min(5, round(1 + proposal.importance * 4))),
            confidence=proposal.confidence,
            source=f"{self.config.source_prefix}:{proposal.source_engine}",
            proposed_by=self.config.proposed_by,
            reason=(
                _optional_text(proposal.metadata.get("reason"))
                or "yisang_memory_proposal"
            ),
            session_id=_optional_text(proposal.metadata.get("session_id")),
            episode_id=_optional_text(proposal.metadata.get("episode_id")),
            continuity_key=_optional_text(
                proposal.metadata.get("continuity_key")
            ),
        )
        proposal_payload = payload.get("proposal")
        if not isinstance(proposal_payload, dict):
            raise ValueError("BIO proposal response must contain proposal object")

        raw_id = proposal_payload.get("id")
        raw_status = str(proposal_payload.get("status") or "pending").casefold()
        status = {
            "pending": "pending",
            "approved": "committed",
            "rejected": "rejected",
            "cancelled": "rejected",
        }.get(raw_status, "pending")
        warnings = proposal_payload.get("validation_warnings", [])
        if not isinstance(warnings, list):
            warnings = []

        return ProviderWriteResult(
            provider_id=self.provider_id,
            status=status,
            proposal_ref=(
                f"bio-proposal:{raw_id}" if raw_id is not None else None
            ),
            reason=str(proposal_payload.get("reason") or ""),
            warnings=tuple(str(item) for item in warnings),
            metadata={
                "bio_status": raw_status,
                "approved_memory_id": proposal_payload.get("approved_memory_id"),
                "project": proposal_payload.get("project"),
                "namespace": proposal_payload.get("namespace"),
                "auto_approved_by_yisang": False,
            },
        )

    def get_current_state(self, topic_key: str) -> ProviderCurrentState:
        payload = self.client.current_state(
            project=self.config.project,
            namespace=self.config.namespace,
            topic_key=topic_key,
        )
        current_id = payload.get("current_memory_id")
        return ProviderCurrentState(
            provider_id=self.provider_id,
            topic_key=topic_key,
            current_memory_id=(
                f"bio:{current_id}" if current_id is not None else None
            ),
            confidence=_bounded_float(payload.get("confidence")),
            superseded_ids=tuple(
                f"bio:{value}" for value in _list(payload.get("superseded_ids"))
            ),
            conflict_ids=tuple(
                f"bio:{value}" for value in _list(payload.get("conflict_ids"))
            ),
            reasoning=str(payload.get("reasoning") or ""),
            candidates=tuple(
                item
                for item in _list(payload.get("candidates"))
                if isinstance(item, dict)
            ),
            metadata={"provider_payload_version": payload.get("version")},
        )

    def get_context(
        self,
        query: str,
        *,
        limit: int = 8,
        char_budget: int = 2400,
    ) -> ProviderContext:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if char_budget <= 0:
            raise ValueError("char_budget must be positive")
        payload = self.client.context_pack(
            query,
            project=self.config.project,
            namespace=self.config.namespace,
            limit=limit,
            char_budget=char_budget,
        )
        memories = tuple(
            record
            for record in map_context_memories(payload)
            if record.is_active()
        )
        diagnostics = payload.get("diagnostics")
        if not isinstance(diagnostics, dict):
            diagnostics = {}
        return ProviderContext(
            provider_id=self.provider_id,
            text=str(payload.get("context") or ""),
            memories=memories,
            context_ref=(
                str(diagnostics["context_pack_id"])
                if diagnostics.get("context_pack_id") is not None
                else None
            ),
            metadata={
                "project": payload.get("project"),
                "namespace": payload.get("namespace"),
                "diagnostics": dict(diagnostics),
                "context_quality_report": payload.get("context_quality_report"),
                "context_reconstruction_report": payload.get(
                    "context_reconstruction_report"
                ),
            },
        )


def _proposal_title(proposal: MemoryProposal) -> str:
    explicit = _optional_text(proposal.metadata.get("title"))
    if explicit:
        return explicit[:160]
    return proposal.content.strip().splitlines()[0][:160]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _bounded_float(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0
