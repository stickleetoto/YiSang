import pytest

from yisang.integrations.bio.client import (
    BioBridgeClientAdapter,
    BioClientConfigurationError,
)
from yisang.integrations.bio.config import BioProviderConfig
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.provider_factory import (
    MemoryProviderSelection,
    build_memory_provider,
)
from yisang.memory.quarantine import InMemoryQuarantinePort


class EmptyBridge:
    def search_memory_with_graph(self, *args, **kwargs):
        return {"results": []}

    def propose_memory_write(self, **kwargs):
        return {"proposal": {"id": 1, "status": "pending"}}

    def resolve_current_state(self, **kwargs):
        return {"current_memory_id": None}

    def build_context_pack(self, *args, **kwargs):
        return {"context": "", "memories": []}


class Client:
    def search(self, *args, **kwargs):
        return {"results": []}

    def propose(self, **kwargs):
        return {"proposal": {"id": 1, "status": "pending"}}

    def current_state(self, **kwargs):
        return {"current_memory_id": None}

    def context_pack(self, *args, **kwargs):
        return {"context": "", "memories": []}


def test_provider_selection_normalizes_name():
    assert MemoryProviderSelection("BIO").provider == "bio"


def test_factory_builds_native_without_importing_bio_runtime():
    memory = InMemoryMemoryPort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )
    provider = build_memory_provider(
        MemoryProviderSelection("native"),
        native_memory=memory,
        native_pipeline=pipeline,
    )
    assert provider.provider_id == "native"


def test_factory_builds_bio_from_injected_client():
    provider = build_memory_provider(
        MemoryProviderSelection("bio"),
        bio_client=Client(),
        bio_config=BioProviderConfig(project="YiSang"),
    )
    assert provider.provider_id == "bio"


def test_bridge_adapter_requires_context_options_contract():
    adapter = BioBridgeClientAdapter(EmptyBridge())
    with pytest.raises(BioClientConfigurationError):
        adapter.context_pack(
            "hello",
            project="YiSang",
            namespace=None,
            limit=3,
            char_budget=100,
        )
