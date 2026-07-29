from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.models import Category, ReadStatus, Tier


class BookSearchResult(BaseModel):
    title: str
    author: str
    cover_url: str | None = None
    description: str | None = None
    open_library_id: str | None = None
    first_publish_year: int | None = None


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    cover_url: str | None
    description: str | None
    category: Category | None
    open_library_id: str | None


class AddToLibraryRequest(BaseModel):
    title: str
    author: str
    cover_url: str | None = None
    description: str | None = None
    category: Category | None = None
    open_library_id: str | None = None
    status: ReadStatus = ReadStatus.BOOKMARKED
    date_completed: date | None = None


class LibraryEntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    status: ReadStatus
    rating: float | None
    tier: Tier | None
    rank_position: int | None
    date_completed: date | None
    created_at: datetime
    book: BookOut


class ComparisonCandidate(BaseModel):
    user_book_id: int
    title: str
    author: str
    cover_url: str | None


class RankRequest(BaseModel):
    tier: Tier


class ChoiceRequest(BaseModel):
    preferred_user_book_id: int


class RankComparison(BaseModel):
    outcome: Literal["comparing"] = "comparing"
    session_id: int
    new_book: ComparisonCandidate
    candidate_book: ComparisonCandidate


class RankPlaced(BaseModel):
    outcome: Literal["placed"] = "placed"
    user_book: LibraryEntryOut


class RecommendationOut(BaseModel):
    title: str
    author: str
    cover_url: str | None
    description: str | None
    open_library_id: str
    similarity: float


class RecommendationsResponse(BaseModel):
    recommendations: list[RecommendationOut]
    message: str | None = None
