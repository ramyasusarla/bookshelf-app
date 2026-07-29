import asyncio

import httpx
from sqlalchemy.orm import Session

from app import open_library
from app.embeddings import average_vectors, generate_embedding
from app.models import Book, Category, RecommendationCandidate, UserBook

# Open Library subject slugs, verified against the live API (checked
# work_count for each before picking) rather than guessed:
#   - REALISTIC_FICTION -> "realistic_fiction" is a real subject but thin
#     (~150 works). Open Library doesn't have a strong equivalent for this
#     school/library-style category, so this genre's candidate pool will
#     usually be small.
#   - MEMOIR -> "memoir" is real but also thin (~330 works).
#   - SELF_HELP -> Open Library has two distinct subjects here: "self-help"
#     (hyphen, ~4k works, canonical display name "self-help") and
#     "self_help" (underscore, ~700 works, display name "self help") as a
#     separate, smaller subject. Picked the larger hyphenated one.
# Everything else (fantasy, science_fiction, mystery, romance,
# historical_fiction, biography, history) mapped cleanly with large pools.
GENRE_SUBJECT_MAP: dict[Category, str] = {
    Category.FANTASY: "fantasy",
    Category.SCI_FI: "science_fiction",
    Category.MYSTERY: "mystery",
    Category.ROMANCE: "romance",
    Category.HISTORICAL_FICTION: "historical_fiction",
    Category.REALISTIC_FICTION: "realistic_fiction",
    Category.BIOGRAPHY: "biography",
    Category.MEMOIR: "memoir",
    Category.SELF_HELP: "self-help",
    Category.HISTORY: "history",
}

SUBJECT_URL = "https://openlibrary.org/subjects/{slug}.json"
COVER_URL = "https://covers.openlibrary.org/b/id/{cover_id}-M.jpg"
CANDIDATES_PER_GENRE = 20
MIN_RATING_FOR_TASTE = 7.0

# Caps concurrent outbound requests (each candidate makes one Open Library
# call + one OpenAI call). Without this, "overall" recommendations on a cold
# cache fan out to up to 10 genres * 20 candidates = ~200 requests at once,
# each opening its own httpx.AsyncClient — this reliably causes
# httpx.ReadTimeout under that load, not just slowness. Verified by
# reproducing the timeout with this cap absent before adding it.
_REQUEST_CONCURRENCY = 5
_request_semaphore = asyncio.Semaphore(_REQUEST_CONCURRENCY)


class Candidate:
    __slots__ = ("open_library_id", "title", "author", "cover_url", "description", "embedding")

    def __init__(
        self,
        open_library_id: str,
        title: str,
        author: str,
        cover_url: str | None,
        description: str | None,
        embedding: list[float],
    ) -> None:
        self.open_library_id = open_library_id
        self.title = title
        self.author = author
        self.cover_url = cover_url
        self.description = description
        self.embedding = embedding


async def _fetch_subject_works(slug: str, limit: int) -> list[dict]:
    async with _request_semaphore:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(SUBJECT_URL.format(slug=slug), params={"limit": limit})
            response.raise_for_status()
            return response.json().get("works", [])


async def _build_candidate(work: dict) -> Candidate | None:
    work_key = work.get("key")
    title = work.get("title")
    if not work_key or not title:
        return None

    authors = work.get("authors") or []
    author = ", ".join(a["name"] for a in authors if a.get("name")) or "Unknown"
    cover_id = work.get("cover_id")
    cover_url = COVER_URL.format(cover_id=cover_id) if cover_id else None

    async with _request_semaphore:
        description = await open_library.fetch_description(work_key)
        embedding_text = description or f"{title} by {author}"
        embedding = await generate_embedding(embedding_text)

    return Candidate(
        open_library_id=work_key,
        title=title,
        author=author,
        cover_url=cover_url,
        description=description,
        embedding=embedding,
    )


def _existing_open_library_ids(db: Session) -> set[str]:
    return {
        row[0]
        for row in db.query(Book.open_library_id).filter(Book.open_library_id.isnot(None)).all()
    }


def _load_cached_candidates(db: Session, category: Category) -> list[Candidate]:
    rows = (
        db.query(RecommendationCandidate)
        .filter(RecommendationCandidate.category == category)
        .all()
    )
    return [
        Candidate(
            open_library_id=row.open_library_id,
            title=row.title,
            author=row.author,
            cover_url=row.cover_url,
            description=row.description,
            embedding=row.embedding,
        )
        for row in rows
    ]


def _save_candidates(db: Session, category: Category, candidates: list[Candidate]) -> None:
    db.query(RecommendationCandidate).filter(RecommendationCandidate.category == category).delete()
    for c in candidates:
        db.add(
            RecommendationCandidate(
                category=category,
                open_library_id=c.open_library_id,
                title=c.title,
                author=c.author,
                cover_url=c.cover_url,
                description=c.description,
                embedding=c.embedding,
            )
        )
    db.commit()


async def fetch_candidates_for_genre(
    db: Session, category: Category, force_refresh: bool = False
) -> list[Candidate]:
    # Note: a genre whose pool is genuinely empty after filtering (e.g. every
    # candidate is already in the library) looks identical to "never fetched"
    # here, so it'll be re-fetched every time. Accepted tradeoff — that
    # re-fetch is just one subject-list call with nothing left to embed, so
    # it's cheap, and avoiding it would need a separate "last fetched at"
    # marker per genre that isn't worth the complexity yet.
    if not force_refresh:
        cached = _load_cached_candidates(db, category)
        if cached:
            return cached

    slug = GENRE_SUBJECT_MAP[category]
    works = await _fetch_subject_works(slug, CANDIDATES_PER_GENRE)

    existing_ids = _existing_open_library_ids(db)
    new_works = [w for w in works if w.get("key") not in existing_ids]

    # Parallelize per-candidate description+embedding fetches — see
    # performance notes: this is still the expensive part of a cold fetch.
    built = await asyncio.gather(*(_build_candidate(w) for w in new_works))
    candidates = [c for c in built if c is not None]

    _save_candidates(db, category, candidates)
    return candidates


async def refresh_candidates(db: Session, category: Category | None) -> list[Category]:
    categories = [category] if category is not None else list(Category)
    await asyncio.gather(
        *(fetch_candidates_for_genre(db, c, force_refresh=True) for c in categories)
    )
    return categories


async def _get_book_embedding(db: Session, book: Book) -> list[float]:
    if book.embedding is not None:
        return book.embedding
    text = book.description or f"{book.title} by {book.author}"
    async with _request_semaphore:
        embedding = await generate_embedding(text)
    book.embedding = embedding
    db.commit()
    return embedding


async def compute_taste_vector(db: Session, category: Category | None) -> list[float] | None:
    query = (
        db.query(UserBook)
        .join(Book)
        .filter(UserBook.rating.isnot(None), UserBook.rating >= MIN_RATING_FOR_TASTE)
    )
    if category is not None:
        query = query.filter(Book.category == category)
    rated_books = [ub.book for ub in query.all()]

    if not rated_books:
        return None

    embeddings = await asyncio.gather(*(_get_book_embedding(db, book) for book in rated_books))
    return average_vectors(embeddings)


async def get_candidate_pool(db: Session, category: Category | None) -> list[Candidate]:
    if category is not None:
        pool = await fetch_candidates_for_genre(db, category)
    else:
        pools = await asyncio.gather(*(fetch_candidates_for_genre(db, c) for c in Category))
        pool = [c for sub in pools for c in sub]

    # Belt-and-suspenders re-filter: a genre's cache may have been built
    # before the user added more books, so re-check against the *current*
    # library rather than trusting the fetch-time filter alone.
    existing_ids = _existing_open_library_ids(db)
    return [c for c in pool if c.open_library_id not in existing_ids]
