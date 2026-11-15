from dataclasses import dataclass


@dataclass(frozen=True)
class Book:
    isbn: str
    title: str


def find_book(books: list[Book], isbn: str) -> Book | None:
    return next((book for book in books if book.isbn == isbn), None)
