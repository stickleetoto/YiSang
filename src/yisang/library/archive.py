from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import Book, LIBRARY_SCHEMA_VERSION, LibraryFormatError
from .port import LibraryPort

LIBRARY_ARCHIVE_SCHEMA_VERSION = 1


def _sha256_json(value: Any) -> str:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_library_archive(port: LibraryPort) -> dict[str, Any]:
    books = [book.to_dict() for book in port.list_books()]
    return {
        "archive_schema_version": LIBRARY_ARCHIVE_SCHEMA_VERSION,
        "library_schema_version": LIBRARY_SCHEMA_VERSION,
        "book_count": len(books),
        "books_sha256": _sha256_json(books),
        "books": books,
    }


def library_digest(port: LibraryPort) -> str:
    return build_library_archive(port)["books_sha256"]


def validate_library_archive(
    archive: dict[str, Any],
) -> tuple[Book, ...]:
    if not isinstance(archive, dict):
        raise LibraryFormatError("library archive root must be an object")
    if (
        archive.get("archive_schema_version")
        != LIBRARY_ARCHIVE_SCHEMA_VERSION
    ):
        raise LibraryFormatError("unsupported library archive schema")
    if archive.get("library_schema_version") != LIBRARY_SCHEMA_VERSION:
        raise LibraryFormatError("unsupported library schema")

    raw_books = archive.get("books")
    if not isinstance(raw_books, list):
        raise LibraryFormatError("library archive books must be an array")

    if archive.get("book_count") != len(raw_books):
        raise LibraryFormatError("library archive book_count mismatch")

    expected = archive.get("books_sha256")
    if not isinstance(expected, str) or len(expected) != 64:
        raise LibraryFormatError("library archive books_sha256 is invalid")
    if _sha256_json(raw_books) != expected:
        raise LibraryFormatError("library archive checksum mismatch")

    books: list[Book] = []
    seen: set[str] = set()
    for raw in raw_books:
        if not isinstance(raw, dict):
            raise LibraryFormatError(
                "library archive Book must be an object"
            )
        book = Book.from_dict(raw)
        if book.book_id in seen:
            raise LibraryFormatError(
                f"duplicate Book id in archive: {book.book_id}"
            )
        seen.add(book.book_id)
        books.append(book)
    return tuple(books)


def restore_library_archive(
    archive: dict[str, Any],
    port: LibraryPort,
    *,
    overwrite: bool = False,
) -> int:
    books = validate_library_archive(archive)

    if not port.is_empty() and not overwrite:
        raise LibraryFormatError(
            "target Library is not empty; pass overwrite=True to replace it"
        )

    if overwrite:
        port.clear()

    for book in books:
        port.put_book(book)
    return len(books)
