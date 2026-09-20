from __future__ import annotations

from .models import Book
from .port import LibraryPort


class InMemoryLibraryPort(LibraryPort):
    def __init__(self, books: tuple[Book, ...] = ()) -> None:
        self._books: dict[str, Book] = {}
        for book in books:
            self.put_book(book)

    def list_books(self) -> tuple[Book, ...]:
        return tuple(
            self._books[book_id]
            for book_id in sorted(self._books)
        )

    def get_book(self, book_id: str) -> Book | None:
        return self._books.get(book_id)

    def put_book(self, book: Book) -> None:
        self._books[book.book_id] = book

    def remove_book(self, book_id: str) -> bool:
        return self._books.pop(book_id, None) is not None

    def clear(self) -> None:
        self._books.clear()
