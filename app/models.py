import enum
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

# text-embedding-3-small's fixed output dimensionality — pgvector needs a
# declared size to size its on-disk storage and (optionally) build an index.
EMBEDDING_DIMENSIONS = 1536


class ReadStatus(str, enum.Enum):
    BOOKMARKED = "bookmarked"
    READING = "reading"
    READ = "read"


class Category(str, enum.Enum):
    FANTASY = "fantasy"
    SCI_FI = "sci_fi"
    MYSTERY = "mystery"
    ROMANCE = "romance"
    HISTORICAL_FICTION = "historical_fiction"
    REALISTIC_FICTION = "realistic_fiction"
    BIOGRAPHY = "biography"
    MEMOIR = "memoir"
    SELF_HELP = "self_help"
    HISTORY = "history"


class Tier(str, enum.Enum):
    """Ranked low to high: a DID_NOT_LIKE entry always ranks below every
    IT_WAS_ALRIGHT entry, which always ranks below every LIKED_IT entry."""

    DID_NOT_LIKE = "did_not_like"
    IT_WAS_ALRIGHT = "it_was_alright"
    LIKED_IT = "liked_it"


class User(Base):
    """A signed-in person (identity managed by Clerk). Rows are created
    lazily on first successful token verification — see app/auth.py."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    clerk_id: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user_books: Mapped[list["UserBook"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("open_library_id", name="uq_books_open_library_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    category: Mapped[Category | None] = mapped_column(Enum(Category), nullable=True)
    open_library_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Cached embedding of description, computed once for the recommendations
    # taste vector and reused forever — a book's description never changes,
    # so there's no invalidation to do. Null when there's no description to
    # embed (see app/normalization.py — a placeholder title/author string is
    # deliberately never embedded as a substitute). pgvector's Vector type
    # round-trips as a plain list[float] through SQLAlchemy, same as the JSON
    # column it replaces — no other code needed to change.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)

    # Global catalog data — shared across all users, not scoped to one.
    user_entries: Mapped[list["UserBook"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )


class UserBook(Base):
    __tablename__ = "user_books"
    __table_args__ = (
        UniqueConstraint(
            "user_id", "category", "rank_position", name="uq_user_books_user_category_rank_position"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    status: Mapped[ReadStatus] = mapped_column(
        Enum(ReadStatus), nullable=False, default=ReadStatus.BOOKMARKED
    )
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[Tier | None] = mapped_column(Enum(Tier), nullable=True)
    # Denormalized copy of book.category, set only once this entry is ranked.
    # Lets the DB enforce rank_position uniqueness per (user, category) — a
    # UNIQUE constraint can't span book.category and user_books.rank_position
    # across two tables — and NULL/NULL/NULL triples for unranked entries
    # don't collide under standard SQL uniqueness semantics.
    category: Mapped[Category | None] = mapped_column(Enum(Category), nullable=True)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_completed: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    user: Mapped["User"] = relationship(back_populates="user_books")
    book: Mapped["Book"] = relationship(back_populates="user_entries")


class RankingSessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RankingSession(Base):
    """Tracks an in-progress binary-search placement of a UserBook into its
    tier's slice of a category's rank_position ordering."""

    __tablename__ = "ranking_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Redundant with user_books.user_id (reachable via user_book_id), but
    # kept directly on this row so ownership checks don't need an extra join.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    user_book_id: Mapped[int] = mapped_column(ForeignKey("user_books.id"), nullable=False)
    tier: Mapped[Tier] = mapped_column(Enum(Tier), nullable=False)
    candidate_user_book_ids: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    lo: Mapped[int] = mapped_column(Integer, nullable=False)
    hi: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[RankingSessionStatus] = mapped_column(
        Enum(RankingSessionStatus),
        nullable=False,
        default=RankingSessionStatus.IN_PROGRESS,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class RecommendationCandidate(Base):
    """Persisted recommendation-candidate cache, keyed by genre. Replaces an
    in-memory dict so a dev-server reload (or any restart) doesn't force a
    full re-fetch + re-embed of every genre's candidate pool."""

    __tablename__ = "recommendation_candidates"
    __table_args__ = (
        UniqueConstraint(
            "category", "open_library_id", name="uq_rec_candidates_category_ol_id"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    category: Mapped[Category] = mapped_column(Enum(Category), nullable=False, index=True)
    open_library_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    author: Mapped[str] = mapped_column(String, nullable=False)
    cover_url: Mapped[str | None] = mapped_column(String, nullable=True)
    description: Mapped[str | None] = mapped_column(String, nullable=True)
    # Nullable: normalize_book() can legitimately produce no embedding_text
    # (no description available) — those candidates are stored so they're not
    # re-fetched every request, but they're excluded from similarity scoring.
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIMENSIONS), nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
