from yisang.integrations.bio.client import BioBridgeClientAdapter
from yisang.integrations.bio.config import BioProviderConfig
from yisang.integrations.bio.mapper import bio_memory_to_yisang
from yisang.integrations.bio.provider import BioMemoryProvider
from yisang.memory.models import MemoryProposal


class Options:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


class Bridge:
    def __init__(self):
        self.proposals = []
        self.approvals = 0

    def search_memory_with_graph(self, query, **kwargs):
        return {
            "results": [
                {"memory": memory_payload(), "score": 0.8},
                {
                    "memory": memory_payload(
                        id=9,
                        status="superseded",
                        content="JSON is current.",
                    ),
                    "score": 0.7,
                },
            ]
        }

    def propose_memory_write(self, **payload):
        self.proposals.append(payload)
        return {
            "proposal": {
                "id": 5,
                "status": "pending",
                "project": payload.get("project"),
                "namespace": payload.get("namespace"),
                "validation_warnings": ["possible_conflict_same_title"],
            }
        }

    def resolve_current_state(self, **kwargs):
        return {
            "current_memory_id": 1,
            "confidence": 0.9,
            "superseded_ids": [9],
            "conflict_ids": [],
            "reasoning": "current",
            "candidates": [],
        }

    def build_context_pack(self, query, *, options):
        return {
            "context": "BIO context",
            "project": options.project,
            "namespace": options.namespace,
            "memories": [memory_payload() | {"score": 0.8}],
            "diagnostics": {"context_pack_id": "ctx-1"},
        }


def memory_payload(**changes):
    payload = {
        "id": 1,
        "memory_type": "decision",
        "title": "Storage",
        "content": "SQLite is current.",
        "importance": 5,
        "confidence": 0.95,
        "source": "user",
        "status": "current",
        "project": "YiSang",
        "namespace": "dev",
    }
    payload.update(changes)
    return payload


def provider_and_bridge():
    bridge = Bridge()
    provider = BioMemoryProvider(
        client=BioBridgeClientAdapter(
            bridge,
            context_options_factory=Options,
        ),
        config=BioProviderConfig(project="YiSang", namespace="dev"),
    )
    return provider, bridge


def test_mapper_preserves_bio_provenance_without_claiming_verified_truth():
    record = bio_memory_to_yisang(memory_payload())
    assert record.memory_id == "bio:1"
    assert record.source_type == "bio_memory"
    assert record.trust_class == "unknown"
    assert record.validation_state == "committed"
    assert record.evidence_refs == ("bio-memory:1",)


def test_superseded_bio_memory_is_inactive():
    record = bio_memory_to_yisang(
        memory_payload(id=9, status="superseded")
    )
    assert record.invalidated is True
    assert record.validation_state == "superseded"
    assert record.is_active() is False


def test_bio_provider_recall_filters_terminal_memory():
    provider, _ = provider_and_bridge()
    records = provider.recall("storage")
    assert [record.memory_id for record in records] == ["bio:1"]


def test_bio_provider_write_creates_pending_proposal_only():
    provider, bridge = provider_and_bridge()
    result = provider.remember(
        MemoryProposal(
            content="Use SQLite.",
            kind="semantic",
            source_engine="test",
            confidence=0.9,
            importance=1.0,
            metadata={
                "title": "Storage",
                "continuity_key": "storage_backend",
            },
        )
    )
    assert result.status == "pending"
    assert result.proposal_ref == "bio-proposal:5"
    assert result.metadata["auto_approved_by_yisang"] is False
    assert bridge.approvals == 0
    assert bridge.proposals[0]["memory_type"] == "project"


def test_bio_current_state_and_context_mapping():
    provider, _ = provider_and_bridge()
    state = provider.get_current_state("storage_backend")
    context = provider.get_context("continue")

    assert state.current_memory_id == "bio:1"
    assert state.superseded_ids == ("bio:9",)
    assert context.context_ref == "ctx-1"
    assert context.text == "BIO context"
    assert context.memories[0].memory_id == "bio:1"
