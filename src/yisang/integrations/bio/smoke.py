from __future__ import annotations

import argparse
import json

from yisang.memory.models import MemoryProposal

from .client import BioBridgeClientAdapter
from .config import BioProviderConfig
from .provider import BioMemoryProvider


class FakeContextPackOptions:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class FakeBioBridge:
    def __init__(self) -> None:
        self.proposal_calls = 0
        self.approval_calls = 0

    def search_memory_with_graph(self, query, **kwargs):
        return {
            "query": query,
            "results": [
                {
                    "memory": _memory_payload(),
                    "score": 0.91,
                    "source": "primary",
                    "via_edge": None,
                }
            ],
            "related_edges": [],
        }

    def propose_memory_write(self, **payload):
        self.proposal_calls += 1
        return {
            "proposal": {
                "id": 77,
                "project": payload.get("project"),
                "namespace": payload.get("namespace"),
                "status": "pending",
                "reason": payload.get("reason"),
                "validation_warnings": [],
                "approved_memory_id": None,
            }
        }

    def resolve_current_state(self, **kwargs):
        return {
            "version": "fake",
            "current_memory_id": 42,
            "confidence": 0.97,
            "superseded_ids": [12],
            "conflict_ids": [],
            "reasoning": "fake current-state resolution",
            "candidates": [{"memory_id": 42, "status": "current"}],
        }

    def build_context_pack(self, query, *, options):
        return {
            "context": f"BIO CONTEXT: {query}",
            "project": options.project,
            "namespace": options.namespace,
            "memories": [_memory_payload() | {"score": 0.91}],
            "diagnostics": {
                "context_pack_id": "ctx_fake_1",
                "context_chars": len(query),
            },
        }


def _memory_payload():
    return {
        "id": 42,
        "project": "YiSang",
        "namespace": "validation",
        "memory_type": "decision",
        "title": "Storage backend",
        "content": "SQLite is the current storage backend.",
        "importance": 5,
        "confidence": 0.98,
        "source": "user",
        "status": "current",
        "success_count": 2,
        "failure_count": 0,
        "continuity_key": "storage_backend",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-bio-adapter-smoke")
    parser.parse_args(argv)

    bridge = FakeBioBridge()
    provider = BioMemoryProvider(
        client=BioBridgeClientAdapter(
            bridge,
            context_options_factory=FakeContextPackOptions,
        ),
        config=BioProviderConfig(
            project="YiSang",
            namespace="validation",
        ),
    )

    recalled = provider.recall("storage backend", limit=3)
    state = provider.get_current_state("storage_backend")
    context = provider.get_context("continue project", limit=3)
    write = provider.remember(
        MemoryProposal(
            content="Next task is Roland import.",
            kind="semantic",
            source_engine="smoke",
            confidence=0.9,
            evidence=["smoke:user"],
            trust_class="trusted",
            metadata={
                "title": "Next task",
                "continuity_key": "next_task",
            },
        )
    )

    payload = {
        "ready": bool(
            len(recalled) == 1
            and recalled[0].memory_id == "bio:42"
            and state.current_memory_id == "bio:42"
            and context.context_ref == "ctx_fake_1"
            and write.status == "pending"
            and write.proposal_ref == "bio-proposal:77"
            and bridge.approval_calls == 0
        ),
        "provider": provider.provider_id,
        "real_bio_used": False,
        "recall_count": len(recalled),
        "current_memory_id": state.current_memory_id,
        "context_memory_count": len(context.memories),
        "write_status": write.status,
        "proposal_ref": write.proposal_ref,
        "proposal_calls": bridge.proposal_calls,
        "approval_calls": bridge.approval_calls,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
