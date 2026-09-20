from __future__ import annotations

import argparse
import json

from yisang.integrations.bio.config import BioProviderConfig
from yisang.integrations.bio.provider import BioMemoryProvider
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.memory.native_provider import NativeMemoryProvider
from yisang.memory.pipeline import MemoryWritePipeline
from yisang.memory.quarantine import InMemoryQuarantinePort

from .evaluator import MemoryProviderABEvaluator
from .scenarios import MemoryValidationScenario


class FixtureBioClient:
    def search(self, query, *, project, namespace, limit):
        text = query.casefold()
        if "storage" in text:
            memories = [_bio_memory(1, "SQLite is the current storage backend.", "current")]
        elif "version" in text:
            memories = [_bio_memory(2, "The corrected next version is v0.6.", "current")]
        else:
            memories = [_bio_memory(3, "Current goal: BIO adapter validation. Next task: runtime provider integration.", "current")]
        return {"results": [{"memory": item, "score": 1.0} for item in memories]}

    def propose(self, **payload):
        return {"proposal": {"id": 1, "status": "pending"}}

    def current_state(self, *, project, namespace, topic_key):
        mapping = {"storage backend": 1, "next version": 2, "next task": 3}
        return {
            "current_memory_id": mapping.get(topic_key),
            "confidence": 1.0,
            "superseded_ids": [90] if topic_key == "storage_backend" else [],
            "conflict_ids": [],
            "reasoning": "fixture current state",
            "candidates": [],
        }

    def context_pack(self, query, *, project, namespace, limit, char_budget):
        result = self.search(
            query,
            project=project,
            namespace=namespace,
            limit=limit,
        )
        memories = [item["memory"] | {"score": item["score"]} for item in result["results"]]
        text = "\n".join(item["content"] for item in memories)[:char_budget]
        return {
            "context": text,
            "project": project,
            "namespace": namespace,
            "memories": memories,
            "diagnostics": {"context_pack_id": "ctx-ab-fixture"},
        }


def _bio_memory(memory_id, content, status):
    return {
        "id": memory_id,
        "memory_type": "decision",
        "title": f"Fixture {memory_id}",
        "content": content,
        "importance": 5,
        "confidence": 1.0,
        "source": "fixture",
        "status": status,
        "project": "YiSang",
        "namespace": "ab",
    }


def _native_provider():
    memory = InMemoryMemoryPort()
    pipeline = MemoryWritePipeline(
        memory=memory,
        governor=MemoryGovernor(),
        quarantine=InMemoryQuarantinePort(),
    )
    provider = NativeMemoryProvider(memory=memory, pipeline=pipeline)

    old_storage = provider.remember(
        MemoryProposal(
            content="storage backend JSON is current",
            confidence=1.0,
            evidence=["fixture:old-storage"],
            trust_class="trusted",
        )
    ).record
    provider.remember(
        MemoryProposal(
            content="storage backend SQLite is the current storage backend.",
            confidence=1.0,
            evidence=["fixture:new-storage"],
            trust_class="trusted",
            supersedes_id=old_storage.memory_id,
        )
    )
    old_version = provider.remember(
        MemoryProposal(
            content="next version is v0.7",
            confidence=1.0,
            evidence=["fixture:old-version"],
            trust_class="trusted",
        )
    ).record
    provider.remember(
        MemoryProposal(
            content="next version corrected next version is v0.6.",
            confidence=1.0,
            evidence=["fixture:new-version"],
            trust_class="trusted",
            supersedes_id=old_version.memory_id,
        )
    )
    provider.remember(
        MemoryProposal(
            content="current goal BIO adapter validation next task runtime provider integration",
            confidence=1.0,
            evidence=["fixture:resume"],
            trust_class="trusted",
        )
    )
    return provider


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="yisang-bio-ab-smoke")
    parser.parse_args(argv)

    native = _native_provider()
    bio = BioMemoryProvider(
        client=FixtureBioClient(),
        config=BioProviderConfig(project="YiSang", namespace="ab"),
    )
    scenarios = (
        MemoryValidationScenario(
            "resume-1",
            "resume",
            "current goal next task",
            required_substrings=("BIO adapter validation", "runtime provider integration"),
            topic_key="next task",
        ),
        MemoryValidationScenario(
            "stale-1",
            "stale",
            "storage backend",
            required_substrings=("SQLite",),
            forbidden_substrings=("JSON is current",),
            topic_key="storage backend",
        ),
        MemoryValidationScenario(
            "correction-1",
            "correction",
            "next version",
            required_substrings=("v0.6",),
            forbidden_substrings=("v0.7",),
            topic_key="next version",
        ),
    )
    report = MemoryProviderABEvaluator().run((native, bio), scenarios)
    payload = {
        "ready": all(summary.pass_rate == 1.0 for summary in report.summaries),
        "real_bio_used": False,
        "scenario_count": len(scenarios),
        "providers": [
            {
                "provider_id": summary.provider_id,
                "passed_count": summary.passed_count,
                "scenario_count": summary.scenario_count,
                "pass_rate": summary.pass_rate,
                "stale_or_forbidden_hits": summary.stale_or_forbidden_hits,
                "total_context_chars": summary.total_context_chars,
            }
            for summary in report.summaries
        ],
        "ranking_produced": False,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
