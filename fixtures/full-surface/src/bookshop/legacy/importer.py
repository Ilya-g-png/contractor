from bookshop.domain.catalog import Book


def import_csv_row(row: str) -> Book:
    isbn, title = row.split(",", 1)
    return Book(isbn=isbn.strip(), title=title.strip())
