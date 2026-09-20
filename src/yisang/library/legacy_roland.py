from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .models import (
    Book,
    KnowledgeEntry,
    LibraryFormatError,
    LibraryUsageNote,
)
from .port import LibraryPort


def _required_str(data: Mapping[str, Any], key: str, *, where: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise LibraryFormatError(f"{where}.{key} must be a non-empty string")
    return value


def _strings(value: Any, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise LibraryFormatError(f"{where} must be an array")
    return tuple(str(item).strip() for item in value if str(item).strip())


def legacy_roland_book_from_dict(
    data: Mapping[str, Any],
    *,
    source_ref: str | None = None,
) -> Book:
    """Convert one legacy Roland book.json payload to YiSang-native models."""

    meta = data.get("book")
    if not isinstance(meta, Mapping):
        raise LibraryFormatError(
            "legacy Roland Book requires a book metadata object"
        )
    raw_entries = data.get("knowledge", [])
    if not isinstance(raw_entries, list):
        raise LibraryFormatError(
            "legacy Roland knowledge must be an array"
        )

    inherited_refs = (source_ref,) if source_ref else ()
    entries: list[KnowledgeEntry] = []
    for raw in raw_entries:
        if not isinstance(raw, Mapping):
            raise LibraryFormatError(
                "legacy Roland knowledge item must be an object"
            )
        complexity = raw.get("complexity", {})
        if not isinstance(complexity, Mapping):
            raise LibraryFormatError(
                "legacy Roland knowledge.complexity must be an object"
            )
        notes = raw.get("usage_notes", [])
        if not isinstance(notes, list):
            raise LibraryFormatError(
                "legacy Roland usage_notes must be an array"
            )

        entry_source_refs = _strings(
            raw.get("source_refs", []),
            where="legacy knowledge.source_refs",
        )
        if not entry_source_refs:
            entry_source_refs = inherited_refs

        entries.append(
            KnowledgeEntry(
                entry_id=_required_str(raw, "id", where="legacy knowledge"),
                title=_required_str(raw, "title", where="legacy knowledge"),
                summary=_required_str(
                    raw,
                    "summary",
                    where="legacy knowledge",
                ),
                aliases=_strings(
                    raw.get("aliases", []),
                    where="legacy knowledge.aliases",
                ),
                tags=_strings(
                    raw.get("tags", []),
                    where="legacy knowledge.tags",
                ),
                use_when=_strings(
                    raw.get("use_when", []),
                    where="legacy knowledge.use_when",
                ),
                avoid_when=_strings(
                    raw.get("avoid_when", []),
                    where="legacy knowledge.avoid_when",
                ),
                structure=_strings(
                    raw.get("structure", []),
                    where="legacy knowledge.structure",
                ),
                tradeoffs=_strings(
                    raw.get("tradeoffs", []),
                    where="legacy knowledge.tradeoffs",
                ),
                complexity={
                    str(key): str(value)
                    for key, value in complexity.items()
                },
                pitfalls=_strings(
                    raw.get("pitfalls", []),
                    where="legacy knowledge.pitfalls",
                ),
                implementation_hint=str(
                    raw.get("implementation_hint", "")
                ).strip(),
                usage_notes=tuple(
                    LibraryUsageNote.from_dict(note)
                    for note in notes
                    if isinstance(note, Mapping)
                ),
                source_refs=entry_source_refs,
                trust_class=str(
                    raw.get("trust_class", "unknown")
                ).strip(),
                validation_state=str(
                    raw.get("validation_state", "imported")
                ).strip(),
            )
        )

    book_source_refs = _strings(
        meta.get("source_refs", []),
        where="legacy book.source_refs",
    )
    if not book_source_refs:
        book_source_refs = inherited_refs

    return Book(
        book_id=_required_str(meta, "id", where="legacy book"),
        title=_required_str(meta, "title", where="legacy book"),
        version=_required_str(meta, "version", where="legacy book"),
        description=str(meta.get("description", "")).strip(),
        entries=tuple(entries),
        source_refs=book_source_refs,
        trust_class=str(meta.get("trust_class", "unknown")).strip(),
        validation_state=str(
            meta.get("validation_state", "imported")
        ).strip(),
    )


def load_legacy_roland_book(path: str | Path) -> Book:
    source = Path(path)
    try:
        raw = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LibraryFormatError(
            f"invalid legacy Roland JSON in {source}: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise LibraryFormatError(
            "legacy Roland Book root must be an object"
        )
    return legacy_roland_book_from_dict(
        raw,
        source_ref=source.as_posix(),
    )


def load_legacy_roland_library(
    book_root: str | Path,
) -> tuple[Book, ...]:
    root = Path(book_root)
    books: list[Book] = []
    seen: set[str] = set()

    if not root.exists():
        return ()

    for path in sorted(root.glob("*/book.json")):
        book = load_legacy_roland_book(path)
        if book.book_id in seen:
            raise LibraryFormatError(
                f"duplicate legacy Roland Book id: {book.book_id}"
            )
        seen.add(book.book_id)
        books.append(book)
    return tuple(books)


def import_legacy_roland_library(
    book_root: str | Path,
    port: LibraryPort,
    *,
    overwrite: bool = False,
) -> int:
    books = load_legacy_roland_library(book_root)

    if not port.is_empty() and not overwrite:
        raise LibraryFormatError(
            "target Library is not empty; pass overwrite=True to replace it"
        )

    if overwrite:
        port.clear()

    for book in books:
        port.put_book(book)
    return len(books)
