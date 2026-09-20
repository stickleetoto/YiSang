from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from yisang.memory.lexical import lexical_terms

from .models import Book, KnowledgeEntry
from .port import LibraryPort

_MIN_SCORE = 4


@dataclass(frozen=True)
class LeanKnowledgeRef:
    book_slot: int
    entry_slot: int


@dataclass(frozen=True)
class LibrarySearchResult:
    book: Book
    entry: KnowledgeEntry
    score: int
    fit: str
    matched_terms: tuple[str, ...]
    reasons: tuple[str, ...]


class CompactLibraryIndex:
    """Derived lexical postings index over authoritative LibraryPort data."""

    def __init__(
        self,
        *,
        books: tuple[Book, ...],
        postings: dict[str, tuple[LeanKnowledgeRef, ...]],
    ) -> None:
        self.books = books
        self.postings = postings

    @classmethod
    def build(cls, port: LibraryPort) -> "CompactLibraryIndex":
        books = port.list_books()
        mutable: dict[str, list[LeanKnowledgeRef]] = {}

        for book_slot, book in enumerate(books):
            for entry_slot, entry in enumerate(book.entries):
                ref = LeanKnowledgeRef(book_slot, entry_slot)
                for term in _index_terms(book, entry):
                    mutable.setdefault(term, []).append(ref)

        postings = {
            term: tuple(sorted(refs, key=lambda ref: (ref.book_slot, ref.entry_slot)))
            for term, refs in mutable.items()
        }
        return cls(books=books, postings=postings)

    def candidate_refs(
        self,
        query_terms: Iterable[str],
    ) -> tuple[LeanKnowledgeRef, ...]:
        refs: set[LeanKnowledgeRef] = set()
        for term in query_terms:
            refs.update(self.postings.get(term, ()))
        return tuple(
            sorted(refs, key=lambda ref: (ref.book_slot, ref.entry_slot))
        )

    def materialize(
        self,
        ref: LeanKnowledgeRef,
    ) -> tuple[Book, KnowledgeEntry]:
        book = self.books[ref.book_slot]
        return book, book.entries[ref.entry_slot]

    def stats(self) -> dict[str, int]:
        return {
            "books": len(self.books),
            "entries": sum(len(book.entries) for book in self.books),
            "terms": len(self.postings),
            "posting_refs": sum(len(refs) for refs in self.postings.values()),
        }


class LexicalLibraryRetriever:
    """Deterministic first-stage Roland retrieval for YiSang v0.6."""

    def __init__(self, port: LibraryPort) -> None:
        self.port = port
        self.index = CompactLibraryIndex.build(port)

    def rebuild(self) -> None:
        self.index = CompactLibraryIndex.build(self.port)

    def search(
        self,
        query: str,
        *,
        limit: int = 3,
    ) -> tuple[LibrarySearchResult, ...]:
        query = query.strip()
        if not query:
            raise ValueError("query must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be positive")

        terms = lexical_terms(query)
        ranked: list[LibrarySearchResult] = []
        for ref in self.index.candidate_refs(terms):
            book, entry = self.index.materialize(ref)
            result = _score(terms, book, entry)
            if result is not None:
                ranked.append(result)

        ranked.sort(
            key=lambda row: (
                -row.score,
                row.fit == "avoid",
                row.book.book_id,
                row.entry.entry_id,
            )
        )
        return tuple(ranked[:limit])


def _index_terms(book: Book, entry: KnowledgeEntry) -> frozenset[str]:
    parts = [
        book.book_id,
        book.title,
        book.description,
        entry.entry_id,
        entry.title,
        entry.summary,
        *entry.aliases,
        *entry.tags,
        *entry.use_when,
        *entry.avoid_when,
        *entry.structure,
        *entry.tradeoffs,
        *entry.pitfalls,
        entry.implementation_hint,
    ]
    return lexical_terms(" ".join(part for part in parts if part))


def _score(
    query_terms: frozenset[str],
    book: Book,
    entry: KnowledgeEntry,
) -> LibrarySearchResult | None:
    reasons: list[str] = []
    matched: set[str] = set()

    def weighted(parts: Iterable[str], weight: int, reason: str) -> int:
        overlap = query_terms & lexical_terms(" ".join(parts))
        if overlap:
            matched.update(overlap)
            reasons.append(reason)
        return len(overlap) * weight

    score = 0
    score += weighted((entry.title, *entry.aliases), 7, "name/alias match")
    score += weighted(entry.tags, 6, "tag match")
    score += weighted((entry.summary,), 4, "summary match")
    score += weighted(entry.use_when, 4, "use-condition match")
    score += weighted(entry.structure, 2, "structure match")
    score += weighted(entry.tradeoffs, 2, "tradeoff match")
    score += weighted(entry.pitfalls, 1, "pitfall match")
    score += weighted((book.title, book.description), 1, "book match")

    anchor_terms = query_terms & lexical_terms(
        " ".join(
            (
                entry.title,
                *entry.aliases,
                *entry.tags,
                entry.summary,
                *entry.use_when,
            )
        )
    )
    avoid_terms = query_terms & lexical_terms(" ".join(entry.avoid_when))
    use_terms = query_terms & lexical_terms(" ".join(entry.use_when))

    if not anchor_terms and not avoid_terms:
        return None
    if score < _MIN_SCORE:
        return None

    if avoid_terms:
        score += len(avoid_terms) * 2
        matched.update(avoid_terms)
        reasons.append("constraint conflict")
        fit = "avoid" if len(avoid_terms) >= max(1, len(use_terms)) else "caution"
    elif use_terms or (
        query_terms
        & lexical_terms(" ".join((entry.title, *entry.aliases, *entry.tags)))
    ):
        fit = "recommended"
    else:
        fit = "caution"

    return LibrarySearchResult(
        book=book,
        entry=entry,
        score=score,
        fit=fit,
        matched_terms=tuple(sorted(matched)),
        reasons=tuple(dict.fromkeys(reasons)),
    )
