"""One-off script: copy real personal data from the old local SQLite DB into
the new Postgres schema.

Only books.py + user_books rows are copied — that's the actual personal
data (library entries, ratings, tiers, rank positions). recommendation
candidates are NOT copied: that table is a pure, regenerable cache (repopulates
automatically on the first /recommendations call per genre), not user data.

Run this AFTER `alembic upgrade head` has created the schema on the target
Postgres database (set via DATABASE_URL), and after signing in through the
real app once so you know your own Clerk user id (the "sub" claim — visible
in the Clerk dashboard under Users, or by decoding a session token).

Usage:
    DATABASE_URL=postgresql+psycopg://... uv run python scripts/migrate_sqlite_data.py \\
        --clerk-id user_xxxxxxxxxxxxxxxxxxxx \\
        --sqlite-path ./bookshelf.db
"""

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# Running this file directly (`python scripts/migrate_sqlite_data.py`) sets
# sys.path[0] to scripts/, not the project root, so `app` isn't importable
# without this — regardless of the caller's cwd or PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import SessionLocal  # noqa: E402
from app.models import Book, User, UserBook  # noqa: E402


def _load_sqlite_rows(sqlite_path: Path) -> tuple[list[dict], list[dict]]:
    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row
    try:
        books = [dict(row) for row in conn.execute("SELECT * FROM books")]
        user_books = [dict(row) for row in conn.execute("SELECT * FROM user_books")]
    finally:
        conn.close()
    return books, user_books


def migrate(sqlite_path: Path, clerk_id: str) -> None:
    old_books, old_user_books = _load_sqlite_rows(sqlite_path)
    print(f"Read {len(old_books)} books and {len(old_user_books)} user_books from {sqlite_path}")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.clerk_id == clerk_id).first()
        if user is None:
            user = User(clerk_id=clerk_id)
            db.add(user)
            db.flush()
        print(f"Migrating into user id={user.id} (clerk_id={clerk_id})")

        old_id_to_new_book: dict[int, int] = {}
        for row in old_books:
            embedding = json.loads(row["embedding"]) if row["embedding"] else None
            book = Book(
                title=row["title"],
                author=row["author"],
                cover_url=row["cover_url"],
                description=row["description"],
                category=row["category"],
                open_library_id=row["open_library_id"],
                embedding=embedding,
            )
            db.add(book)
            db.flush()
            old_id_to_new_book[row["id"]] = book.id

        for row in old_user_books:
            db.add(
                UserBook(
                    user_id=user.id,
                    book_id=old_id_to_new_book[row["book_id"]],
                    status=row["status"],
                    rating=row["rating"],
                    tier=row["tier"],
                    category=row["category"],
                    rank_position=row["rank_position"],
                    date_completed=row["date_completed"],
                    created_at=row["created_at"],
                )
            )

        db.commit()
        print(f"Migrated {len(old_books)} books and {len(old_user_books)} library entries.")
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clerk-id", required=True, help="Your real Clerk user id (the 'sub' claim)")
    parser.add_argument(
        "--sqlite-path",
        default="./bookshelf.db",
        help="Path to the old SQLite DB (default: ./bookshelf.db)",
    )
    args = parser.parse_args()
    migrate(Path(args.sqlite_path), args.clerk_id)
