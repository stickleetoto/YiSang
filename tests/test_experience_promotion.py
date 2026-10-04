from yisang.experience import (
    ExperienceObservation,
    ExperiencePromotionEngine,
    InMemoryExperiencePort,
    SQLiteExperiencePort,
)
from yisang.library.in_memory import InMemoryLibraryPort
from yisang.library.models import Book, KnowledgeEntry


def _library() -> InMemoryLibraryPort:
    return InMemoryLibraryPort(
        (
            Book(
                book_id="book.python",
                title="Python Core",
                version="1",
                entries=(
                    KnowledgeEntry(
                        entry_id="pytest-debug",
                        title="Debug pytest failures",
                        summary=(
                            "Inspect the first causal failure before broad edits."
                        ),
                    ),
                ),
            ),
        )
    )


def _observation(
    index: int,
    *,
    outcome: str = "success",
    risk_class: str = "normal",
) -> ExperienceObservation:
    return ExperienceObservation(
        evidence_id=f"ev-{index}",
        target_book_id="book.python",
        target_entry_id="pytest-debug",
        lesson=(
            "Read the first failing traceback before changing multiple files."
        ),
        applies_when=("pytest fails",),
        outcome=outcome,
        verified=True,
        verification_ref=f"verify-{index}",
        risk_class=risk_class,
    )


def test_three_distinct_verified_successes_promote_usage_note():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=3,
    )

    first = engine.observe(_observation(1))
    second = engine.observe(_observation(2))
    third = engine.observe(_observation(3))

    assert first.status == "recorded"
    assert second.status == "recorded"
    assert third.status == "promoted"
    assert third.promoted is True

    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert len(entry.usage_notes) == 1
    note = entry.usage_notes[0]
    assert note.successful_uses == 3
    assert note.verification == ("verify-1", "verify-2", "verify-3")


def test_duplicate_evidence_does_not_inflate_success_count():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=2,
    )

    first = engine.observe(_observation(1))
    duplicate = engine.observe(_observation(1))

    assert first.candidate is not None
    assert first.candidate.success_count == 1
    assert duplicate.status == "duplicate"
    assert duplicate.candidate is not None
    assert duplicate.candidate.success_count == 1


def test_failure_evidence_blocks_automatic_promotion():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=2,
    )

    engine.observe(_observation(1))
    failed = engine.observe(_observation(2, outcome="failure"))
    later = engine.observe(_observation(3))

    assert failed.status == "needs_review"
    assert later.status == "needs_review"
    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert entry.usage_notes == ()


def test_privileged_candidate_is_recorded_but_never_auto_promoted():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=1,
    )

    result = engine.observe(
        _observation(1, risk_class="privileged")
    )

    assert result.status == "blocked"
    assert result.reason == "automatic_promotion_forbidden_for_risk_class"
    assert result.candidate is not None
    assert result.candidate.status == "blocked"
    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert entry.usage_notes == ()


def test_unverified_observation_is_not_persisted():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=1,
    )

    result = engine.observe(
        ExperienceObservation(
            evidence_id="ev-unverified",
            target_book_id="book.python",
            target_entry_id="pytest-debug",
            lesson="Never promote this directly.",
            verified=False,
        )
    )

    assert result.status == "rejected"
    assert store.all() == ()


def test_missing_target_blocks_without_inventing_library_content():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=1,
    )

    result = engine.observe(
        ExperienceObservation(
            evidence_id="ev-missing",
            target_book_id="book.missing",
            target_entry_id="missing",
            lesson="Do not invent a target.",
            verified=True,
            verification_ref="verify-missing",
        )
    )

    assert result.status == "blocked"
    assert result.reason == "target_knowledge_not_found"
    assert result.candidate is not None
    assert result.candidate.status == "blocked"


def test_sqlite_candidate_survives_restart_and_third_success_promotes(
    tmp_path,
):
    library = _library()
    path = tmp_path / "experience.db"

    first_engine = ExperiencePromotionEngine(
        experience=SQLiteExperiencePort(path),
        library=library,
        min_successes=3,
    )
    first_engine.observe(_observation(1))
    first_engine.observe(_observation(2))

    restarted_store = SQLiteExperiencePort(path)
    restarted_engine = ExperiencePromotionEngine(
        experience=restarted_store,
        library=library,
        min_successes=3,
    )
    result = restarted_engine.observe(_observation(3))

    assert result.status == "promoted"
    assert result.candidate is not None
    assert result.candidate.success_count == 3
    assert len(restarted_store.all()) == 1


def test_additional_success_reinforces_existing_usage_note():
    library = _library()
    store = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=store,
        library=library,
        min_successes=2,
    )

    engine.observe(_observation(1))
    promoted = engine.observe(_observation(2))
    reinforced = engine.observe(_observation(3))

    assert promoted.promoted is True
    assert reinforced.reinforced is True
    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert len(entry.usage_notes) == 1
    assert entry.usage_notes[0].successful_uses == 3
