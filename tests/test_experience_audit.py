import pytest

from yisang.experience import (
    ExperienceObservation,
    ExperiencePromotionEngine,
    InMemoryExperiencePort,
    InMemoryPromotionAuditPort,
    PromotionAuditPort,
    SQLitePromotionAuditPort,
)
from yisang.library.in_memory import InMemoryLibraryPort
from yisang.library.models import Book, KnowledgeEntry, LibraryUsageNote


LESSON = "Read the first failing traceback before broad edits."
APPLIES = ("pytest fails",)


def _library(
    *,
    existing_note: LibraryUsageNote | None = None,
) -> InMemoryLibraryPort:
    notes = () if existing_note is None else (existing_note,)
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
                        summary="Use causal evidence before broad edits.",
                        usage_notes=notes,
                    ),
                ),
            ),
        )
    )


def _observation(
    evidence_id: str,
    *,
    verification_ref: str = "verify:1",
) -> ExperienceObservation:
    return ExperienceObservation(
        evidence_id=evidence_id,
        target_book_id="book.python",
        target_entry_id="pytest-debug",
        lesson=LESSON,
        applies_when=APPLIES,
        verified=True,
        verification_ref=verification_ref,
    )


def test_promotion_records_audit_and_revoke_removes_new_note():
    experience = InMemoryExperiencePort()
    library = _library()
    audit = InMemoryPromotionAuditPort()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
        audit_port=audit,
    )

    promoted = engine.observe(_observation("ev-1"))

    assert promoted.status == "promoted"
    assert [item.operation for item in audit.all()] == ["promote"]
    first = audit.all()[0]
    assert first.before_note is None
    assert first.after_note is not None
    assert first.evidence_ids == ("ev-1",)

    revoked = engine.revoke(
        promoted.candidate.candidate_key,
        actor="reviewer",
        reason="lesson was too broad",
    )

    assert revoked.status == "revoked"
    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert entry.usage_notes == ()
    candidate = experience.get(promoted.candidate.candidate_key)
    assert candidate is not None
    assert candidate.status == "revoked"
    assert [item.operation for item in audit.all()] == [
        "promote",
        "revoke",
    ]


def test_revoked_candidate_cannot_silently_repromote():
    experience = InMemoryExperiencePort()
    library = _library()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
    )
    promoted = engine.observe(_observation("ev-1"))
    engine.revoke(
        promoted.candidate.candidate_key,
        actor="reviewer",
        reason="revoke it",
    )

    later = engine.observe(
        _observation("ev-2", verification_ref="verify:2")
    )

    assert later.status == "blocked"
    assert later.reason == "candidate_revoked"
    assert later.candidate is not None
    assert later.candidate.success_count == 1


def test_revoke_after_reinforcement_restores_preexisting_note():
    original = LibraryUsageNote(
        note=LESSON,
        applies_when=APPLIES,
        successful_uses=5,
        verification=("legacy:1",),
    )
    experience = InMemoryExperiencePort()
    library = _library(existing_note=original)
    audit = InMemoryPromotionAuditPort()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
        audit_port=audit,
    )

    promoted = engine.observe(_observation("ev-1"))
    assert promoted.reinforced is True

    current = library.get_entry(
        "book.python",
        "pytest-debug",
    ).usage_notes[0]
    assert current.successful_uses == 5
    assert current.verification == ("legacy:1", "verify:1")

    revoked = engine.revoke(
        promoted.candidate.candidate_key,
        actor="reviewer",
        reason="restore baseline",
    )

    assert revoked.status == "revoked"
    restored = library.get_entry(
        "book.python",
        "pytest-debug",
    ).usage_notes[0]
    assert restored == original


def test_revoke_fails_closed_if_current_usage_note_diverged():
    experience = InMemoryExperiencePort()
    library = _library()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
    )
    promoted = engine.observe(_observation("ev-1"))
    candidate_key = promoted.candidate.candidate_key

    book = library.get_book("book.python")
    entry = library.get_entry("book.python", "pytest-debug")
    changed = LibraryUsageNote(
        note=LESSON,
        applies_when=APPLIES,
        successful_uses=99,
        verification=("manual:newer",),
    )
    changed_entry = type(entry)(
        entry_id=entry.entry_id,
        title=entry.title,
        summary=entry.summary,
        aliases=entry.aliases,
        tags=entry.tags,
        use_when=entry.use_when,
        avoid_when=entry.avoid_when,
        structure=entry.structure,
        tradeoffs=entry.tradeoffs,
        complexity=entry.complexity,
        pitfalls=entry.pitfalls,
        implementation_hint=entry.implementation_hint,
        usage_notes=(changed,),
        source_refs=entry.source_refs,
        trust_class=entry.trust_class,
        validation_state=entry.validation_state,
        schema_version=entry.schema_version,
    )
    changed_book = type(book)(
        book_id=book.book_id,
        title=book.title,
        version=book.version,
        description=book.description,
        entries=(changed_entry,),
        source_refs=book.source_refs,
        trust_class=book.trust_class,
        validation_state=book.validation_state,
        schema_version=book.schema_version,
    )
    library.put_book(changed_book)

    result = engine.revoke(
        candidate_key,
        actor="reviewer",
        reason="attempt rollback",
    )

    assert result.status == "conflict"
    assert result.reason == "current_usage_note_diverged"
    candidate = experience.get(candidate_key)
    assert candidate is not None
    assert candidate.status == "promoted"
    assert library.get_entry(
        "book.python",
        "pytest-debug",
    ).usage_notes[0] == changed


def test_sqlite_audit_survives_restart(tmp_path):
    path = tmp_path / "promotion-audit.db"
    audit = SQLitePromotionAuditPort(path)
    experience = InMemoryExperiencePort()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=_library(),
        min_successes=1,
        audit_port=audit,
    )

    promoted = engine.observe(_observation("ev-1"))
    candidate_key = promoted.candidate.candidate_key

    reopened = SQLitePromotionAuditPort(path)
    records = reopened.for_candidate(candidate_key)

    assert len(records) == 1
    assert records[0].operation == "promote"
    assert records[0].candidate_key == candidate_key
    assert records[0].after_note is not None


class _FailingAudit(PromotionAuditPort):
    def append(self, mutation):
        raise RuntimeError("audit unavailable")

    def all(self):
        return ()


def test_audit_write_failure_compensates_library_and_candidate():
    experience = InMemoryExperiencePort()
    library = _library()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
        audit_port=_FailingAudit(),
    )
    observation = _observation("ev-1")

    with pytest.raises(RuntimeError, match="audit unavailable"):
        engine.observe(observation)

    entry = library.get_entry("book.python", "pytest-debug")
    assert entry is not None
    assert entry.usage_notes == ()
    candidate = experience.get(observation.candidate_key)
    assert candidate is not None
    assert candidate.status == "candidate"
    assert candidate.success_count == 1


def test_revoke_requires_audited_promotion_chain():
    experience = InMemoryExperiencePort()
    library = _library()
    engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
    )
    promoted = engine.observe(_observation("ev-1"))

    fresh_engine = ExperiencePromotionEngine(
        experience=experience,
        library=library,
        min_successes=1,
        audit_port=InMemoryPromotionAuditPort(),
    )
    result = fresh_engine.revoke(
        promoted.candidate.candidate_key,
        actor="reviewer",
        reason="cannot prove original mutation",
    )

    assert result.status == "blocked"
    assert result.reason == "missing_promotion_audit"
