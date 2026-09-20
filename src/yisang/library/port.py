from __future__ import annotations

from abc import ABC, abstractmethod

from .models import Book, KnowledgeEntry


class LibraryPort(ABC):
    """Authoritative YiSang Library storage boundary.

    Retrieval indexes are derived projections and should not become the source
    of truth. Implementations must expose deterministic Book enumeration.
    """

    @abstractmethod
    def list_books(self) -> tuple[Book, ...]:
        raise NotImplementedError

    @abstractmethod
    def get_book(self, book_id: str) -> Book | None:
        raise NotImplementedError

    @abstractmethod
    def put_book(self, book: Book) -> None:
        raise NotImplementedError

    @abstractmethod
    def remove_book(self, book_id: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def clear(self) -> None:
        raise NotImplementedError

    def get_entry(
        self,
        book_id: str,
        entry_id: str,
    ) -> KnowledgeEntry | None:
        book = self.get_book(book_id)
        if book is None:
            return None
        for entry in book.entries:
            if entry.entry_id == entry_id:
                return entry
        return None

    def is_empty(self) -> bool:
        return not self.list_books()
