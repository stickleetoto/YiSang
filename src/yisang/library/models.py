from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

LIBRARY_SCHEMA_VERSION = 1


class LibraryFormatError(ValueError):
    """Raised when Library data violates the YiSang Library contract."""


def _required_str(data: Mapping[str, Any], key: str, *, where: str) -> str:
    value = str(data.get(key, "")).strip()
    if not value:
        raise LibraryFormatError(f"{where}.{key} must be a non-empty string")
    return value


def _strings(value: Any, *, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise LibraryFormatError(f"{where} must be an array")
    return tuple(str(item).strip() for item in value if str(item).strip())


@dataclass(frozen=True)
class LibraryUsageNote:
    """Compatibility model for legacy Roland Usage Notes.

    YiSang v0.6 can preserve imported durable notes, but creating/promoting new
    Usage Notes belongs to the later Experience Promotion phase.
    """

    note: str
    applies_when: tuple[str, ...] = ()
    successful_uses: int = 0
    verification: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.note.strip():
            raise LibraryFormatError("usage_note.note must be non-empty")
        if self.successful_uses < 1:
            raise LibraryFormatError("usage_note.successful_uses must be >= 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "note": self.note,
            "applies_when": list(self.applies_when),
            "successful_uses": self.successful_uses,
            "verification": list(self.verification),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "LibraryUsageNote":
        return cls(
            note=_required_str(data, "note", where="usage_note"),
            applies_when=_strings(
                data.get("applies_when", ()),
                where="usage_note.applies_when",
            ),
            successful_uses=int(data.get("successful_uses", 0)),
            verification=_strings(
                data.get("verification", ()),
                where="usage_note.verification",
            ),
        )


@dataclass(frozen=True)
class KnowledgeEntry:
    entry_id: str
    title: str
    summary: str
    aliases: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    use_when: tuple[str, ...] = ()
    avoid_when: tuple[str, ...] = ()
    structure: tuple[str, ...] = ()
    tradeoffs: tuple[str, ...] = ()
    complexity: Mapping[str, str] = field(default_factory=dict)
    pitfalls: tuple[str, ...] = ()
    implementation_hint: str = ""
    usage_notes: tuple[LibraryUsageNote, ...] = ()
    source_refs: tuple[str, ...] = ()
    trust_class: str = "unknown"
    validation_state: str = "imported"
    schema_version: int = LIBRARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.entry_id.strip():
            raise LibraryFormatError("knowledge.entry_id must be non-empty")
        if not self.title.strip():
            raise LibraryFormatError("knowledge.title must be non-empty")
        if not self.summary.strip():
            raise LibraryFormatError("knowledge.summary must be non-empty")
        if self.schema_version <= 0:
            raise LibraryFormatError("knowledge.schema_version must be positive")
        if not self.trust_class.strip():
            raise LibraryFormatError("knowledge.trust_class must be non-empty")
        if not self.validation_state.strip():
            raise LibraryFormatError(
                "knowledge.validation_state must be non-empty"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "title": self.title,
            "summary": self.summary,
            "aliases": list(self.aliases),
            "tags": list(self.tags),
            "use_when": list(self.use_when),
            "avoid_when": list(self.avoid_when),
            "structure": list(self.structure),
            "tradeoffs": list(self.tradeoffs),
            "complexity": dict(self.complexity),
            "pitfalls": list(self.pitfalls),
            "implementation_hint": self.implementation_hint,
            "usage_notes": [note.to_dict() for note in self.usage_notes],
            "source_refs": list(self.source_refs),
            "trust_class": self.trust_class,
            "validation_state": self.validation_state,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "KnowledgeEntry":
        complexity = data.get("complexity", {})
        if not isinstance(complexity, Mapping):
            raise LibraryFormatError("knowledge.complexity must be an object")
        notes = data.get("usage_notes", ())
        if not isinstance(notes, (list, tuple)):
            raise LibraryFormatError("knowledge.usage_notes must be an array")

        return cls(
            entry_id=_required_str(data, "entry_id", where="knowledge"),
            title=_required_str(data, "title", where="knowledge"),
            summary=_required_str(data, "summary", where="knowledge"),
            aliases=_strings(data.get("aliases", ()), where="knowledge.aliases"),
            tags=_strings(data.get("tags", ()), where="knowledge.tags"),
            use_when=_strings(
                data.get("use_when", ()),
                where="knowledge.use_when",
            ),
            avoid_when=_strings(
                data.get("avoid_when", ()),
                where="knowledge.avoid_when",
            ),
            structure=_strings(
                data.get("structure", ()),
                where="knowledge.structure",
            ),
            tradeoffs=_strings(
                data.get("tradeoffs", ()),
                where="knowledge.tradeoffs",
            ),
            complexity={
                str(key): str(value)
                for key, value in complexity.items()
            },
            pitfalls=_strings(
                data.get("pitfalls", ()),
                where="knowledge.pitfalls",
            ),
            implementation_hint=str(
                data.get("implementation_hint", "")
            ).strip(),
            usage_notes=tuple(
                LibraryUsageNote.from_dict(note)
                for note in notes
                if isinstance(note, Mapping)
            ),
            source_refs=_strings(
                data.get("source_refs", ()),
                where="knowledge.source_refs",
            ),
            trust_class=str(data.get("trust_class", "unknown")).strip(),
            validation_state=str(
                data.get("validation_state", "imported")
            ).strip(),
            schema_version=int(
                data.get("schema_version", LIBRARY_SCHEMA_VERSION)
            ),
        )


@dataclass(frozen=True)
class Book:
    book_id: str
    title: str
    version: str
    description: str = ""
    entries: tuple[KnowledgeEntry, ...] = ()
    source_refs: tuple[str, ...] = ()
    trust_class: str = "unknown"
    validation_state: str = "imported"
    schema_version: int = LIBRARY_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not self.book_id.strip():
            raise LibraryFormatError("book.book_id must be non-empty")
        if not self.title.strip():
            raise LibraryFormatError("book.title must be non-empty")
        if not self.version.strip():
            raise LibraryFormatError("book.version must be non-empty")
        if self.schema_version <= 0:
            raise LibraryFormatError("book.schema_version must be positive")
        if not self.trust_class.strip():
            raise LibraryFormatError("book.trust_class must be non-empty")
        if not self.validation_state.strip():
            raise LibraryFormatError("book.validation_state must be non-empty")

        seen: set[str] = set()
        for entry in self.entries:
            if entry.entry_id in seen:
                raise LibraryFormatError(
                    f"duplicate knowledge entry id in Book: {entry.entry_id}"
                )
            seen.add(entry.entry_id)

    def to_dict(self) -> dict[str, Any]:
        return {
            "book_id": self.book_id,
            "title": self.title,
            "version": self.version,
            "description": self.description,
            "entries": [entry.to_dict() for entry in self.entries],
            "source_refs": list(self.source_refs),
            "trust_class": self.trust_class,
            "validation_state": self.validation_state,
            "schema_version": self.schema_version,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Book":
        entries = data.get("entries", ())
        if not isinstance(entries, (list, tuple)):
            raise LibraryFormatError("book.entries must be an array")

        parsed_entries: list[KnowledgeEntry] = []
        for raw in entries:
            if not isinstance(raw, Mapping):
                raise LibraryFormatError(
                    "book.entries items must be objects"
                )
            parsed_entries.append(KnowledgeEntry.from_dict(raw))

        return cls(
            book_id=_required_str(data, "book_id", where="book"),
            title=_required_str(data, "title", where="book"),
            version=_required_str(data, "version", where="book"),
            description=str(data.get("description", "")).strip(),
            entries=tuple(parsed_entries),
            source_refs=_strings(
                data.get("source_refs", ()),
                where="book.source_refs",
            ),
            trust_class=str(data.get("trust_class", "unknown")).strip(),
            validation_state=str(
                data.get("validation_state", "imported")
            ).strip(),
            schema_version=int(
                data.get("schema_version", LIBRARY_SCHEMA_VERSION)
            ),
        )
