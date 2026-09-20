from __future__ import annotations

from yisang.context.compiler import ContextCompiler
from yisang.core.models import YiSangRequest
from yisang.core.runtime import YiSangRuntime
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity.models import AgentState, IdentityCharter
from yisang.integrations.bio.client import BioMemoryClient
from yisang.integrations.bio.config import BioProviderConfig
from yisang.integrations.bio.provider import BioMemoryProvider
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.verification.base import PassThroughVerifier


class RuntimeBioClient(BioMemoryClient):
    def __init__(self) -> None:
        self.proposals: list[dict] = []

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
                        "source": "user",
                        "status": "current",
                        "project": project,
                        "namespace": namespace,
                    },
                    "score": 0.95,
                }
            ]
        }

    def propose(self, **payload):
        self.proposals.append(payload)
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
            "reasoning": "fixture",
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
                    "source": "user",
                    "status": "current",
                    "project": project,
                    "namespace": namespace,
                    "score": 0.95,
                }
            ],
            "diagnostics": {"context_pack_id": "ctx-runtime-bio"},
        }


def _runtime(*, memory_provider=None):
    engines = EngineRouter()
    engines.register(EchoEngine("small", "SMALL"))
    return YiSangRuntime(
        identity=IdentityCharter("provider-runtime", "YiSang"),
        state=AgentState(active_engine="small"),
        memory=InMemoryMemoryPort(),
        governor=MemoryGovernor(),
        ego_registry=EgoRegistry(),
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        memory_provider=memory_provider,
    )


def test_runtime_defaults_to_native_provider():
    response = _runtime().run(YiSangRequest("native-1", "hello"))
    assert response.memory_provider_id == "native"
    assert response.memory_context_ref is None


def test_runtime_reads_from_bio_provider_without_replacing_native_storage():
    client = RuntimeBioClient()
    provider = BioMemoryProvider(
        client=client,
        config=BioProviderConfig(project="YiSang", namespace="runtime"),
    )
    response = _runtime(memory_provider=provider).run(
        YiSangRequest("bio-1", "storage backend")
    )
    assert response.memory_provider_id == "bio"
    assert response.memory_context_ref == "ctx-runtime-bio"
    assert response.used_memory_ids == ["bio:42"]
    assert "1 memories" in response.text


def test_runtime_bio_write_stays_pending():
    client = RuntimeBioClient()
    provider = BioMemoryProvider(
        client=client,
        config=BioProviderConfig(project="YiSang", namespace="runtime"),
    )
    response = _runtime(memory_provider=provider).run(
        YiSangRequest("bio-2", "remember: next task is resume evaluator")
    )
    assert response.memory_write_results[0]["provider_id"] == "bio"
    assert response.memory_write_results[0]["status"] == "pending"
    assert response.memory_write_results[0]["proposal_ref"] == "bio-proposal:88"
    assert response.memory_write_results[0]["memory_id"] is None
    assert len(client.proposals) == 1
