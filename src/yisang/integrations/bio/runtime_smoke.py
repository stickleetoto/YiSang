from __future__ import annotations

import argparse
import json

from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier

from .config import BioProviderConfig
from .provider import BioMemoryProvider


class RuntimeSmokeBioClient:
    def __init__(self) -> None:
        self.proposal_count = 0

    def search(self, query, *, project, namespace, limit):
        return {
            "results": [
                {
                    "memory": {
                        "id": 42,
                        "memory_type": "decision",
                        "title": "Current storage",
                        "content": "SQLite is the current storage backend.",
                        "importance": 5,
                        "confidence": 0.98,
                        "source": "fixture",
                        "status": "current",
                        "project": project,
                        "namespace": namespace,
                    },
                    "score": 0.95,
                }
            ]
        }

    def propose(self, **payload):
        self.proposal_count += 1
        return {
            "proposal": {
                "id": 88,
                "status": "pending",
                "project": payload.get("project"),
                "namespace": payload.get("namespace"),
                "validation_warnings": [],
            }
        }

    def current_state(self, *, project, namespace, topic_key):
        return {
            "current_memory_id": 42,
            "confidence": 0.98,
            "superseded_ids": [],
            "conflict_ids": [],
            "reasoning": "runtime smoke fixture",
            "candidates": [],
        }

    def context_pack(self, query, *, project, namespace, limit, char_budget):
        return {
            "context": "BIO managed context",
            "project": project,
            "namespace": namespace,
            "memories": [
                {
                    "id": 42,
                    "memory_type": "decision",
                    "title": "Current storage",
                    "content": "SQLite is the current storage backend.",
                    "importance": 5,
                    "confidence": 0.98,
                    "source": "fixture",
                    "status": "current",
                    "project": project,
                    "namespace": namespace,
                    "score": 0.95,
                }
            ],
            "diagnostics": {"context_pack_id": "ctx-runtime-smoke"},
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-bio-runtime-smoke")
    parser.parse_args(argv)

    client = RuntimeSmokeBioClient()
    provider = BioMemoryProvider(
        client=client,
        config=BioProviderConfig(
            project="YiSang",
            namespace="runtime-smoke",
        ),
    )
    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))
    runtime = YiSangRuntime(
        identity=IdentityCharter("bio-runtime-smoke", "YiSang"),
        state=AgentState(active_engine="small"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        memory_provider=provider,
    )

    read = runtime.run(
        YiSangRequest("bio-runtime-read", "storage backend")
    )
    write = runtime.run(
        YiSangRequest(
            "bio-runtime-write",
            "remember: next task is A/B validation",
        )
    )
    write_item = write.memory_write_results[0] if write.memory_write_results else {}

    payload = {
        "ready": bool(
            read.memory_provider_id == "bio"
            and read.memory_context_ref == "ctx-runtime-smoke"
            and read.used_memory_ids == ["bio:42"]
            and write_item.get("provider_id") == "bio"
            and write_item.get("status") == "pending"
            and write_item.get("proposal_ref") == "bio-proposal:88"
            and client.proposal_count == 1
        ),
        "real_bio_used": False,
        "memory_provider_id": read.memory_provider_id,
        "memory_context_ref": read.memory_context_ref,
        "used_memory_ids": read.used_memory_ids,
        "write_status": write_item.get("status"),
        "proposal_ref": write_item.get("proposal_ref"),
        "proposal_count": client.proposal_count,
        "direct_bio_approval": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
