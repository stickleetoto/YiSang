from __future__ import annotations

from dataclasses import replace

import pytest

from yisang.experience import (
    EgoInstructionPatchAdapter,
    ExperienceEvidence,
    InMemoryPromotionLedger,
    LessonCandidate,
    LibraryKnowledgeApplyAdapter,
    PromotionApplicationError,
    PromotionApplyRequest,
    PromotionGate,
    ReplayCaseResult,
    ReplayReport,
    SQLitePromotionPort,
)
from yisang.library import Book, InMemoryLibraryPort


def _artifact(*, target: str = "library_knowledge"):
    candidate = LessonCandidate(
        candidate_id=f"candidate-{target}",
        kind="knowledge" if target == "library_knowledge" else "procedure",
        target=target,
        title="Validated lesson",
        proposed_content="Prefer a verified exact result over an unverified guess.",
        source_episode_ids=("episode-1",),
        source_evidence=(
            ExperienceEvidence(
                evidence_ref="test:replay:1",
                source_type="test_result",
                summary="replay passed",
                verified=True,
            ),
        ),
        trigger_conditions=("exact result is available",),
        validation_tests=("replay-1",),
        success_count=2,
        scope="reasoning",
        risk_class="normal",
        version="2",
    )
    replay = ReplayReport(
        candidate_id=candidate.candidate_id,
        results=(ReplayCaseResult(test_id="replay-1", passed=True),),
    )
    outcome = PromotionGate().promote(candidate, replay)
    assert outcome.artifact is not None
    return outcome.artifact


def _request(artifact_id: str, target_ref: str) -> PromotionApplyRequest:
    return PromotionApplyRequest(
        artifact_id=artifact_id,
        target_ref=target_ref,
        actor="human-reviewer",
        approval_ref="approval:review:1",
        reason="reviewed validated promotion",
    )


def test_sqlite_promotion_port_round_trip_and_invalidation(tmp_path) -> None:
    artifact = _artifact()
    db = tmp_path / "promotions.db"

    with SQLitePromotionPort(db) as port:
        port.put(artifact)
        loaded = port.get(artifact.artifact_id)
        assert loaded is not None
        assert loaded.content == artifact.content
        assert loaded.trigger_conditions == artifact.trigger_conditions
        assert loaded.scope == "reasoning"
        assert loaded.risk_class == "normal"

        invalidated = port.invalidate(
            artifact.artifact_id,
            reason="later replay disproved it",
        )
        assert invalidated.active is False

    with SQLitePromotionPort(db) as reopened:
        persisted = reopened.get(artifact.artifact_id)
        assert persisted is not None
        assert persisted.active is False
        assert persisted.invalidation_reason == "later replay disproved it"


def test_library_adapter_applies_promoted_knowledge_with_provenance() -> None:
    artifact = _artifact()
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    library = InMemoryLibraryPort(
        (
            Book(
                book_id="experience",
                title="Experience",
                version="1",
            ),
        )
    )

    receipt = LibraryKnowledgeApplyAdapter(promotions, library).apply(
        _request(artifact.artifact_id, "library_book:experience"),
        book_id="experience",
    )

    assert receipt.status == "applied"
    entry = library.get_entry(
        "experience",
        f"promoted-{artifact.artifact_id}",
    )
    assert entry is not None
    assert entry.summary == artifact.content
    assert entry.use_when == artifact.trigger_conditions
    assert f"promotion:{artifact.artifact_id}" in entry.source_refs
    assert entry.validation_state == "promoted"
    assert entry.trust_class == "verified"


def test_library_apply_is_idempotent_for_same_artifact_and_target() -> None:
    artifact = _artifact()
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    library = InMemoryLibraryPort(
        (Book(book_id="experience", title="Experience", version="1"),)
    )
    adapter = LibraryKnowledgeApplyAdapter(promotions, library)
    request = _request(artifact.artifact_id, "library_book:experience")

    first = adapter.apply(request, book_id="experience")
    second = adapter.apply(request, book_id="experience")

    assert first.status == "applied"
    assert second.status == "already_applied"
    assert len(library.get_book("experience").entries) == 1
    assert len(promotions.receipts(artifact.artifact_id)) == 1


def test_invalidated_artifact_cannot_be_applied() -> None:
    artifact = _artifact()
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    promotions.invalidate(artifact.artifact_id, reason="revoked")
    library = InMemoryLibraryPort(
        (Book(book_id="experience", title="Experience", version="1"),)
    )

    with pytest.raises(PromotionApplicationError, match="not active"):
        LibraryKnowledgeApplyAdapter(promotions, library).apply(
            _request(artifact.artifact_id, "library_book:experience"),
            book_id="experience",
        )


def test_library_adapter_rejects_wrong_target_ref() -> None:
    artifact = _artifact()
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    library = InMemoryLibraryPort(
        (Book(book_id="experience", title="Experience", version="1"),)
    )

    with pytest.raises(PromotionApplicationError, match="target_ref"):
        LibraryKnowledgeApplyAdapter(promotions, library).apply(
            _request(artifact.artifact_id, "library_book:wrong"),
            book_id="experience",
        )


def test_ego_adapter_builds_patch_without_mutating_registry() -> None:
    artifact = _artifact(target="ego_procedure")
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)

    patch = EgoInstructionPatchAdapter(promotions).build_patch(
        _request(artifact.artifact_id, "ego:file-ops"),
        ego_id="file-ops",
    )

    assert patch.artifact_id == artifact.artifact_id
    assert patch.ego_id == "file-ops"
    assert patch.instruction == artifact.content
    assert patch.version == "2"
    assert patch.approval_ref == "approval:review:1"


def test_library_adapter_rejects_ego_artifact() -> None:
    artifact = _artifact(target="ego_instruction")
    promotions = InMemoryPromotionLedger()
    promotions.put(artifact)
    library = InMemoryLibraryPort(
        (Book(book_id="experience", title="Experience", version="1"),)
    )

    with pytest.raises(PromotionApplicationError, match="not supported"):
        LibraryKnowledgeApplyAdapter(promotions, library).apply(
            _request(artifact.artifact_id, "library_book:experience"),
            book_id="experience",
        )


def test_sqlite_receipt_survives_restart(tmp_path) -> None:
    artifact = _artifact()
    db = tmp_path / "promotions.db"
    library = InMemoryLibraryPort(
        (Book(book_id="experience", title="Experience", version="1"),)
    )

    with SQLitePromotionPort(db) as port:
        port.put(artifact)
        receipt = LibraryKnowledgeApplyAdapter(port, library).apply(
            _request(artifact.artifact_id, "library_book:experience"),
            book_id="experience",
        )
        assert receipt.status == "applied"

    with SQLitePromotionPort(db) as reopened:
        receipts = reopened.receipts(artifact.artifact_id)
        assert len(receipts) == 1
        assert receipts[0].approval_ref == "approval:review:1"
        assert receipts[0].result_ref.endswith(
            f"promoted-{artifact.artifact_id}"
        )
