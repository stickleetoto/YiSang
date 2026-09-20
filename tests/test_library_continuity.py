import json

import pytest

from yisang.context.compiler import ContextCompiler
from yisang.core.runtime import YiSangRuntime
from yisang.ego.models import EgoManifest
from yisang.ego.registry import EgoRegistry
from yisang.ego.router import CapabilityRouter
from yisang.engines.demo import EchoEngine
from yisang.engines.router import EngineRouter
from yisang.identity import (
    AgentState,
    IdentityCharter,
    build_continuity_bundle,
    build_identity_snapshot,
    load_continuity_bundle,
    restore_continuity_bundle,
    validate_snapshot_against_runtime,
    write_continuity_bundle,
)
from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    library_digest,
)
from yisang.memory.governor import MemoryGovernor
from yisang.memory.in_memory import InMemoryMemoryPort
from yisang.memory.models import MemoryProposal
from yisang.verification.base import PassThroughVerifier


def _library():
    return InMemoryLibraryPort(
        (
            Book(
                book_id="graph",
                title="Graph Algorithms",
                version="1",
                entries=(
                    KnowledgeEntry(
                        entry_id="dijkstra",
                        title="Heap Dijkstra",
                        summary="Use a priority queue for non-negative shortest paths.",
                        aliases=("shortest path",),
                        tags=("graph", "dijkstra"),
                        use_when=("edge weights are non-negative",),
                        avoid_when=("negative edge weights are possible",),
                        source_refs=("book://graph",),
                        trust_class="curated",
                        validation_state="validated",
                    ),
                ),
            ),
        )
    )


def _runtime(*, with_state=True, with_library=True):
    memory = InMemoryMemoryPort()
    egos = EgoRegistry()
    if with_state:
        memory.commit(
            MemoryProposal(
                content="library continuity memory",
                source_engine="seed",
                confidence=0.95,
                evidence=["library-continuity:seed"],
                trust_class="verified",
                writer="governor",
            )
        )
        egos.register(
            EgoManifest(
                ego_id="ego.debug",
                name="Debug",
                provides=("debug",),
                keywords=("bug",),
            )
        )
        state = AgentState(
            active_engine="engine-a",
            active_project="YiSang",
            current_goal="preserve Roland continuity",
            tags={"phase": "v0.6"},
        )
    else:
        state = AgentState(active_engine="engine-a")

    engines = EngineRouter()
    engines.register(EchoEngine("engine-a", "A"))
    engines.register(EchoEngine("engine-b", "B"))

    return YiSangRuntime(
        identity=IdentityCharter("yisang-001", "YiSang"),
        state=state,
        memory=memory,
        governor=MemoryGovernor(),
        ego_registry=egos,
        capability_router=CapabilityRouter(),
        context_compiler=ContextCompiler(),
        engine_router=engines,
        verifier=PassThroughVerifier(),
        library_port=_library() if with_library else None,
    )


def test_snapshot_captures_authoritative_library_digest():
    runtime = _runtime()

    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )

    assert snapshot.library is not None
    assert snapshot.library.kind == "library"
    assert snapshot.library.ref == "library://authoritative"
    assert snapshot.library.sha256 == library_digest(runtime.library_port)
    assert snapshot.library.schema_version == 1


def test_snapshot_runtime_validation_detects_library_drift():
    runtime = _runtime()
    snapshot = build_identity_snapshot(
        runtime,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )

    runtime.library_port.put_book(
        Book(
            book_id="extra",
            title="Extra",
            version="1",
            entries=(
                KnowledgeEntry(
                    entry_id="extra-entry",
                    title="Extra Entry",
                    summary="Drifted Library content.",
                ),
            ),
        )
    )

    report = validate_snapshot_against_runtime(snapshot, runtime)

    assert report.valid is False
    assert any("Library digest" in error for error in report.errors)


def test_continuity_bundle_round_trip_carries_library_archive(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )

    assert bundle.snapshot.library is not None
    assert bundle.library_archive is not None
    assert bundle.library_archive["book_count"] == 1
    assert (
        bundle.library_archive["books_sha256"]
        == bundle.snapshot.library.sha256
    )

    path = write_continuity_bundle(bundle, tmp_path / "continuity-v06.json")
    loaded = load_continuity_bundle(path)

    assert loaded.library_archive is not None
    assert loaded.library_archive["books_sha256"] == bundle.snapshot.library.sha256


def test_bundle_restore_rehydrates_library_and_rebuilds_retriever():
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )
    target = _runtime(with_state=False, with_library=False)

    report = restore_continuity_bundle(
        bundle,
        target,
        target_engine="engine-b",
        memory_factory=InMemoryMemoryPort,
        library_factory=InMemoryLibraryPort,
    )

    assert report.continuity_preserved is True
    assert report.library_restored is True
    assert target.library_port is not None
    assert [book.book_id for book in target.library_port.list_books()] == ["graph"]
    assert target.library_retriever is not None

    results = target.library_retriever.search("Dijkstra shortest path")
    assert results
    assert results[0].entry.entry_id == "dijkstra"
    assert report.evidence["library_book_count"] == 1
    assert report.evidence["post_library_sha256"] == bundle.snapshot.library.sha256


def test_bundle_rejects_library_tampering_with_valid_outer_checksum(tmp_path):
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )
    path = write_continuity_bundle(bundle, tmp_path / "continuity-v06.json")
    raw = json.loads(path.read_text(encoding="utf-8"))

    raw["payload"]["library_archive"]["books"][0]["title"] = "Tampered"
    raw["payload_sha256"] = _payload_sha(raw["payload"])
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(ValueError, match="Library archive checksum mismatch|library archive checksum mismatch"):
        load_continuity_bundle(path)


def test_bundle_restore_requires_empty_staging_library():
    source = _runtime()
    bundle = build_continuity_bundle(
        source,
        policy_version="policy-v1",
        runtime_version="0.6-dev",
    )
    target = _runtime(with_state=False, with_library=False)

    with pytest.raises(ValueError, match="empty staging LibraryPort"):
        restore_continuity_bundle(
            bundle,
            target,
            target_engine="engine-b",
            memory_factory=InMemoryMemoryPort,
            library_factory=_library,
        )

    assert target.library_port is None
    assert target.state.active_engine == "engine-a"


def _payload_sha(payload):
    import hashlib

    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
