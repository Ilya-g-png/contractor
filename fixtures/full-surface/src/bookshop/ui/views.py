from bookshop.domain.catalog import Book


def render_book(book: Book) -> str:
    return f"{book.title} ({book.isbn})"
