from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import open_library
from app.auth import get_current_user
from app.database import get_db
from app.normalization import normalize_book
from app.models import (
    Book,
    Category,
    RankingSession,
    RankingSessionStatus,
    ReadStatus,
    Tier,
    User,
    UserBook,
)
from app.schemas import (
    AddToLibraryRequest,
    BookSearchResult,
    ChoiceRequest,
    ComparisonCandidate,
    LibraryEntryOut,
    RankComparison,
    RankPlaced,
    RankRequest,
)

router = APIRouter()

TIER_ORDER = [Tier.DID_NOT_LIKE, Tier.IT_WAS_ALRIGHT, Tier.LIKED_IT]

# rating is derived from a book's standing within its tier, never set directly.
TIER_RATING_RANGES: dict[Tier, tuple[float, float]] = {
    Tier.DID_NOT_LIKE: (1.0, 3.9),
    Tier.IT_WAS_ALRIGHT: (4.0, 6.9),
    Tier.LIKED_IT: (7.0, 10.0),
}


@router.get("/books/search", response_model=list[BookSearchResult])
async def search_books(q: str = Query(..., min_length=1)) -> list[BookSearchResult]:
    return await open_library.search_books(q)


@router.post("/library", response_model=LibraryEntryOut, status_code=201)
async def add_to_library(
    payload: AddToLibraryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserBook:
    # Book is the shared, global catalog — reused across every user's library.
    book = None
    if payload.open_library_id:
        book = (
            db.query(Book)
            .filter(Book.open_library_id == payload.open_library_id)
            .first()
        )
    if book is None:
        description = payload.description
        if description is None and payload.open_library_id:
            description = await open_library.fetch_description(payload.open_library_id)
        record = normalize_book(
            title=payload.title,
            open_library_id=payload.open_library_id,
            raw_authors=payload.author,
            cover_url=payload.cover_url,
            description=description,
        )
        book = Book(
            title=record.title,
            author=record.author,
            cover_url=record.cover_url,
            description=record.description,
            category=payload.category or record.category_guess,
            open_library_id=record.open_library_id,
        )
        db.add(book)
        db.flush()

    user_book = UserBook(
        user_id=current_user.id,
        book_id=book.id,
        status=payload.status,
        date_completed=payload.date_completed,
    )
    db.add(user_book)
    db.commit()
    db.refresh(user_book)
    return user_book


@router.get("/library", response_model=list[LibraryEntryOut])
def list_library(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> list[UserBook]:
    return (
        db.query(UserBook)
        .filter(UserBook.user_id == current_user.id)
        .order_by(UserBook.created_at.desc())
        .all()
    )


def _category_book_ids(category: Category):
    return select(Book.id).where(Book.category == category).scalar_subquery()


def _tier_start_position(db: Session, user_id: int, category: Category, tier: Tier) -> int:
    lower_tiers = TIER_ORDER[: TIER_ORDER.index(tier)]
    if not lower_tiers:
        return 1
    count = (
        db.query(UserBook)
        .filter(
            UserBook.user_id == user_id,
            UserBook.book_id.in_(_category_book_ids(category)),
            UserBook.tier.in_(lower_tiers),
        )
        .count()
    )
    return 1 + count


def _tier_candidates(db: Session, user_id: int, category: Category, tier: Tier) -> list[UserBook]:
    return (
        db.query(UserBook)
        .filter(
            UserBook.user_id == user_id,
            UserBook.book_id.in_(_category_book_ids(category)),
            UserBook.tier == tier,
        )
        .order_by(UserBook.rank_position.asc())
        .all()
    )


def _recompute_tier_ratings(db: Session, user_id: int, category: Category, tier: Tier) -> None:
    lo, hi = TIER_RATING_RANGES[tier]
    members = _tier_candidates(db, user_id, category, tier)  # ascending rank_position: worst -> best
    n = len(members)
    for local_rank, member in enumerate(members, start=1):
        if n == 1:
            member.rating = round((lo + hi) / 2, 2)
        else:
            member.rating = round(lo + (hi - lo) * (local_rank - 1) / (n - 1), 2)


def _to_candidate(user_book: UserBook) -> ComparisonCandidate:
    return ComparisonCandidate(
        user_book_id=user_book.id,
        title=user_book.book.title,
        author=user_book.book.author,
        cover_url=user_book.book.cover_url,
    )


def _place_book(db: Session, user_book: UserBook, tier: Tier, position: int) -> None:
    category = user_book.book.category
    user_id = user_book.user_id

    # Shift highest rank_position first: with a UNIQUE(user_id, category,
    # rank_position) constraint, a single batched UPDATE can momentarily
    # duplicate a position mid-statement depending on row-processing order
    # (e.g. moving 3->4 before the existing 4 has moved to 5). Updating
    # highest-to-lowest always frees the target slot before anything else
    # claims it.
    shifted_ids = [
        row.id
        for row in db.query(UserBook.id)
        .filter(
            UserBook.user_id == user_id,
            UserBook.book_id.in_(_category_book_ids(category)),
            UserBook.rank_position >= position,
        )
        .order_by(UserBook.rank_position.desc())
        .all()
    ]
    for shifted_id in shifted_ids:
        db.execute(
            update(UserBook)
            .where(UserBook.id == shifted_id)
            .values(rank_position=UserBook.rank_position + 1)
        )

    user_book.tier = tier
    user_book.category = category
    user_book.rank_position = position
    user_book.status = ReadStatus.READ
    try:
        db.flush()
        _recompute_tier_ratings(db, user_id, category, tier)
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="rank position conflict, likely a concurrent ranking session — please retry",
        )
    db.refresh(user_book)


def _get_user_book_or_404(db: Session, user_id: int, user_book_id: int) -> UserBook:
    # Scoped by user_id so a mismatched owner 404s rather than leaking
    # another user's row's existence.
    user_book = (
        db.query(UserBook)
        .filter(UserBook.id == user_book_id, UserBook.user_id == user_id)
        .first()
    )
    if user_book is None:
        raise HTTPException(status_code=404, detail="library entry not found")
    return user_book


def _get_ranking_session_or_404(db: Session, user_id: int, session_id: int) -> RankingSession:
    session = (
        db.query(RankingSession)
        .filter(RankingSession.id == session_id, RankingSession.user_id == user_id)
        .first()
    )
    if session is None:
        raise HTTPException(status_code=404, detail="ranking session not found")
    return session


@router.post("/library/{user_book_id}/rank", response_model=RankComparison | RankPlaced)
def start_ranking(
    user_book_id: int,
    payload: RankRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RankComparison | RankPlaced:
    user_book = _get_user_book_or_404(db, current_user.id, user_book_id)
    if user_book.tier is not None:
        raise HTTPException(status_code=400, detail="book is already ranked")
    if user_book.book.category is None:
        raise HTTPException(status_code=400, detail="book must have a category before ranking")

    tier = payload.tier
    candidates = _tier_candidates(db, current_user.id, user_book.book.category, tier)

    if not candidates:
        position = _tier_start_position(db, current_user.id, user_book.book.category, tier)
        _place_book(db, user_book, tier, position)
        return RankPlaced(user_book=user_book)

    session = RankingSession(
        user_id=current_user.id,
        user_book_id=user_book.id,
        tier=tier,
        candidate_user_book_ids=[c.id for c in candidates],
        lo=0,
        hi=len(candidates),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    mid = (session.lo + session.hi) // 2
    return RankComparison(
        session_id=session.id,
        new_book=_to_candidate(user_book),
        candidate_book=_to_candidate(candidates[mid]),
    )


@router.get("/library/rank-sessions/{session_id}", response_model=RankComparison)
def get_ranking_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RankComparison:
    session = _get_ranking_session_or_404(db, current_user.id, session_id)
    if session.status != RankingSessionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="ranking session already completed")

    new_user_book = _get_user_book_or_404(db, current_user.id, session.user_book_id)
    mid = (session.lo + session.hi) // 2
    candidate = _get_user_book_or_404(db, current_user.id, session.candidate_user_book_ids[mid])
    return RankComparison(
        session_id=session.id,
        new_book=_to_candidate(new_user_book),
        candidate_book=_to_candidate(candidate),
    )


@router.post(
    "/library/rank-sessions/{session_id}/choice",
    response_model=RankComparison | RankPlaced,
)
def submit_ranking_choice(
    session_id: int,
    payload: ChoiceRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RankComparison | RankPlaced:
    session = _get_ranking_session_or_404(db, current_user.id, session_id)
    if session.status != RankingSessionStatus.IN_PROGRESS:
        raise HTTPException(status_code=400, detail="ranking session already completed")

    candidates = session.candidate_user_book_ids
    mid = (session.lo + session.hi) // 2
    candidate_id = candidates[mid]

    if payload.preferred_user_book_id == session.user_book_id:
        session.lo = mid + 1
    elif payload.preferred_user_book_id == candidate_id:
        session.hi = mid
    else:
        raise HTTPException(
            status_code=400,
            detail="preferred_user_book_id must be one of the two books just presented",
        )
    db.commit()
    db.refresh(session)

    new_user_book = _get_user_book_or_404(db, current_user.id, session.user_book_id)

    if session.lo < session.hi:
        next_mid = (session.lo + session.hi) // 2
        next_candidate = _get_user_book_or_404(db, current_user.id, candidates[next_mid])
        return RankComparison(
            session_id=session.id,
            new_book=_to_candidate(new_user_book),
            candidate_book=_to_candidate(next_candidate),
        )

    idx = session.lo
    tier_start = _tier_start_position(db, current_user.id, new_user_book.book.category, session.tier)
    position = tier_start + idx
    _place_book(db, new_user_book, session.tier, position)

    session.status = RankingSessionStatus.COMPLETED
    db.commit()
    return RankPlaced(user_book=new_user_book)
