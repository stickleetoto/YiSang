from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from yisang.library import (
    Book,
    InMemoryLibraryPort,
    KnowledgeEntry,
    LibraryFormatError,
    build_library_archive,
    import_legacy_roland_library,
    legacy_roland_book_from_dict,
    library_digest,
    restore_library_archive,
    validate_library_archive,
)


LEGACY_BOOK = {
    "book": {
        "id": "python-core",
        "title": "Python Core",
        "version": "0.3.0",
        "description": "Dense reusable Python knowledge for testing migration.",
    },
    "knowledge": [
        {
            "id": "bounded-concurrency",
            "title": "Bounded concurrency",
            "summary": "Bound parallel I/O work so resources are not exhausted.",
            "aliases": ["semaphore"],
            "tags": ["asyncio", "concurrency"],
            "use_when": ["many independent I/O operations"],
            "avoid_when": ["strict serial ordering is required"],
            "structure": ["fixed concurrency limit"],
            "tradeoffs": ["throughput versus resource pressure"],
            "complexity": {"active": "O(limit)"},
            "pitfalls": ["do not pre-create unbounded tasks"],
            "implementation_hint": "Use a semaphore or worker pool.",
            "usage_notes": [],
        }
    ],
}


def test_legacy_roland_import_preserves_book_and_entry_shape() -> None:
    book = legacy_roland_book_from_dict(
        LEGACY_BOOK,
        source_ref="legacy://roland/python-core",
    )

    assert book.book_id == "python-core"
    assert book.title == "Python Core"
    assert book.source_refs == ("legacy://roland/python-core",)
    assert len(book.entries) == 1

    entry = book.entries[0]
    assert entry.entry_id == "bounded-concurrency"
    assert entry.tags == ("asyncio", "concurrency")
    assert entry.source_refs == ("legacy://roland/python-core",)
    assert entry.validation_state == "imported"


def test_legacy_import_rejects_duplicate_entry_ids() -> None:
    raw = copy.deepcopy(LEGACY_BOOK)
    raw["knowledge"].append(copy.deepcopy(raw["knowledge"][0]))

    with pytest.raises(LibraryFormatError, match="duplicate knowledge entry"):
        legacy_roland_book_from_dict(raw)


def test_in_memory_library_has_deterministic_book_order() -> None:
    first = Book(
        book_id="a-book",
        title="A",
        version="1",
        entries=(
            KnowledgeEntry(
                entry_id="a",
                title="A",
                summary="A reusable entry.",
            ),
        ),
    )
    second = Book(
        book_id="z-book",
        title="Z",
        version="1",
        entries=(
            KnowledgeEntry(
                entry_id="z",
                title="Z",
                summary="Another reusable entry.",
            ),
        ),
    )
    port = InMemoryLibraryPort((second, first))

    assert [book.book_id for book in port.list_books()] == [
        "a-book",
        "z-book",
    ]
    assert port.get_entry("z-book", "z").title == "Z"


def test_library_archive_digest_is_insertion_order_independent() -> None:
    first = legacy_roland_book_from_dict(
        LEGACY_BOOK,
        source_ref="legacy://one",
    )
    raw = copy.deepcopy(LEGACY_BOOK)
    raw["book"]["id"] = "testing-debugging"
    raw["book"]["title"] = "Testing and Debugging"
    raw["knowledge"][0]["id"] = "regression-first"
    second = legacy_roland_book_from_dict(
        raw,
        source_ref="legacy://two",
    )

    left = InMemoryLibraryPort((first, second))
    right = InMemoryLibraryPort((second, first))

    assert library_digest(left) == library_digest(right)


def test_library_archive_round_trip() -> None:
    source = InMemoryLibraryPort(
        (
            legacy_roland_book_from_dict(
                LEGACY_BOOK,
                source_ref="legacy://roland/python-core",
            ),
        )
    )
    archive = build_library_archive(source)
    target = InMemoryLibraryPort()

    restored = restore_library_archive(archive, target)

    assert restored == 1
    assert target.list_books() == source.list_books()
    assert library_digest(target) == library_digest(source)


def test_library_archive_detects_tampering() -> None:
    source = InMemoryLibraryPort(
        (legacy_roland_book_from_dict(LEGACY_BOOK),)
    )
    archive = build_library_archive(source)
    tampered = copy.deepcopy(archive)
    tampered["books"][0]["title"] = "Tampered"

    with pytest.raises(LibraryFormatError, match="checksum mismatch"):
        validate_library_archive(tampered)


def test_restore_refuses_nonempty_target_without_overwrite() -> None:
    source = InMemoryLibraryPort(
        (legacy_roland_book_from_dict(LEGACY_BOOK),)
    )
    archive = build_library_archive(source)
    target = InMemoryLibraryPort(source.list_books())

    with pytest.raises(LibraryFormatError, match="not empty"):
        restore_library_archive(archive, target)


def test_directory_import_uses_file_path_as_source_ref(
    tmp_path: Path,
) -> None:
    book_dir = tmp_path / "books" / "python-core"
    book_dir.mkdir(parents=True)
    book_path = book_dir / "book.json"
    book_path.write_text(
        json.dumps(LEGACY_BOOK),
        encoding="utf-8",
    )
    port = InMemoryLibraryPort()

    imported = import_legacy_roland_library(
        tmp_path / "books",
        port,
    )

    assert imported == 1
    book = port.get_book("python-core")
    assert book is not None
    assert book.source_refs == (book_path.as_posix(),)
    assert book.entries[0].source_refs == (book_path.as_posix(),)
