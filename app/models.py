import enum
from datetime import date, datetime

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
    # Cached embedding of description (or title/author if no description),
    # computed once for the recommendations taste vector and reused forever —
    # a book's description never changes, so there's no invalidation to do.
    embedding: Mapped[list[float] | None] = mapped_column(JSON, nullable=True)

    user_entries: Mapped[list["UserBook"]] = relationship(
        back_populates="book", cascade="all, delete-orphan"
    )


class UserBook(Base):
    __tablename__ = "user_books"
    __table_args__ = (
        UniqueConstraint(
            "category", "rank_position", name="uq_user_books_category_rank_position"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"), nullable=False)
    status: Mapped[ReadStatus] = mapped_column(
        Enum(ReadStatus), nullable=False, default=ReadStatus.BOOKMARKED
    )
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    tier: Mapped[Tier | None] = mapped_column(Enum(Tier), nullable=True)
    # Denormalized copy of book.category, set only once this entry is ranked.
    # Lets the DB enforce rank_position uniqueness per category (a UNIQUE
    # constraint can't span book.category and user_books.rank_position across
    # two tables), and NULL/NULL pairs for unranked entries don't collide
    # under standard SQL uniqueness semantics.
    category: Mapped[Category | None] = mapped_column(Enum(Category), nullable=True)
    rank_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    date_completed: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    book: Mapped["Book"] = relationship(back_populates="user_entries")


class RankingSessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class RankingSession(Base):
    """Tracks an in-progress binary-search placement of a UserBook into its
    tier's slice of a category's rank_position ordering."""

    __tablename__ = "ranking_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
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
    embedding: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
