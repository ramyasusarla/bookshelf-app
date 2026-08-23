import asyncio

import httpx
from sqlalchemy.orm import Session

from app import open_library
from app.embeddings import average_vectors, generate_embeddings_batch, record_cache_hit, record_cache_miss
from app.models import Book, Category, RecommendationCandidate, UserBook
from app.normalization import GENRE_SUBJECT_MAP, normalize_book

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
        embedding: list[float] | None,
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


async def _fetch_description_capped(work_key: str) -> str | None:
    async with _request_semaphore:
        return await open_library.fetch_description(work_key)


async def _build_candidates_batch(works: list[dict]) -> list[Candidate]:
    """Build Candidates for a whole genre's worth of new works in one pass:
    descriptions are still fetched with the existing per-request concurrency
    cap (Open Library rate-limit protection), but every candidate that needs
    an embedding is embedded in a single batched OpenAI call instead of one
    call per candidate."""
    valid_works = [w for w in works if w.get("key") and w.get("title")]
    if not valid_works:
        return []

    descriptions = await asyncio.gather(
        *(_fetch_description_capped(w["key"]) for w in valid_works)
    )

    records = [
        normalize_book(
            title=work["title"],
            open_library_id=work["key"],
            raw_authors=work.get("authors"),
            cover_url=COVER_URL.format(cover_id=work["cover_id"]) if work.get("cover_id") else None,
            description=description,
        )
        for work, description in zip(valid_works, descriptions)
    ]

    texts_to_embed = [r.embedding_text for r in records if r.embedding_text is not None]
    new_embeddings = await generate_embeddings_batch(texts_to_embed)
    record_cache_miss(len(texts_to_embed))
    embeddings_iter = iter(new_embeddings)

    return [
        Candidate(
            open_library_id=record.open_library_id,
            title=record.title,
            author=record.author,
            cover_url=record.cover_url,
            description=record.description,
            embedding=next(embeddings_iter) if record.embedding_text is not None else None,
        )
        for record in records
    ]


def _user_library_open_library_ids(db: Session, user_id: int) -> set[str]:
    """Open Library IDs already in this specific user's library. The
    recommendation-candidate cache itself is global (shared across users —
    see RecommendationCandidate), so "already have this" can only be
    evaluated per user, at read time, not baked into the shared cache."""
    return {
        row[0]
        for row in db.query(Book.open_library_id)
        .join(UserBook, UserBook.book_id == Book.id)
        .filter(UserBook.user_id == user_id, Book.open_library_id.isnot(None))
        .all()
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
            # Serving this genre's whole pool from the DB avoids re-embedding
            # every candidate in it — each one is an avoided OpenAI call.
            record_cache_hit(sum(1 for c in cached if c.embedding is not None))
            return cached

    slug = GENRE_SUBJECT_MAP[category]
    works = await _fetch_subject_works(slug, CANDIDATES_PER_GENRE)

    candidates = await _build_candidates_batch(works)

    _save_candidates(db, category, candidates)
    return candidates


async def refresh_candidates(db: Session, category: Category | None) -> list[Category]:
    categories = [category] if category is not None else list(Category)
    await asyncio.gather(
        *(fetch_candidates_for_genre(db, c, force_refresh=True) for c in categories)
    )
    return categories


async def compute_taste_vector(
    db: Session, user_id: int, category: Category | None
) -> list[float] | None:
    query = (
        db.query(UserBook)
        .join(Book)
        .filter(
            UserBook.user_id == user_id,
            UserBook.rating.isnot(None),
            UserBook.rating >= MIN_RATING_FOR_TASTE,
        )
    )
    if category is not None:
        query = query.filter(Book.category == category)
    rated_books = [ub.book for ub in query.all()]

    if not rated_books:
        return None

    already_cached = [b for b in rated_books if b.embedding is not None]
    record_cache_hit(len(already_cached))

    # No description to embed against — skip rather than embedding a weak
    # title/author placeholder string (see app/normalization.py).
    needs_embedding = [b for b in rated_books if b.embedding is None and b.description]
    if needs_embedding:
        new_embeddings = await generate_embeddings_batch([b.description for b in needs_embedding])
        record_cache_miss(len(needs_embedding))
        for book, embedding in zip(needs_embedding, new_embeddings):
            book.embedding = embedding
        db.commit()

    usable_embeddings = [b.embedding for b in rated_books if b.embedding is not None]
    return average_vectors(usable_embeddings)


async def get_top_candidates(
    db: Session,
    user_id: int,
    category: Category | None,
    taste_vector: list[float],
    limit: int,
) -> list[tuple[Candidate, float]]:
    """Ensure the relevant genre(s)' candidate pools are cached, then rank
    them against taste_vector with a single DB-side pgvector query instead of
    pulling every embedding into Python and scoring it there — the ordering
    itself, not just storage, now lives in Postgres."""
    categories = [category] if category is not None else list(Category)
    # fetch_candidates_for_genre's return value isn't needed here — this call
    # just guarantees RecommendationCandidate has an up-to-date pool for each
    # genre before the SQL query below reads it.
    await asyncio.gather(*(fetch_candidates_for_genre(db, c) for c in categories))

    # The candidate cache is global/shared across users, so "already have
    # this" is filtered per-user here at read time, not baked into the cache.
    existing_ids = _user_library_open_library_ids(db, user_id)

    distance = RecommendationCandidate.embedding.cosine_distance(taste_vector)
    query = (
        db.query(RecommendationCandidate, distance.label("distance"))
        .filter(
            RecommendationCandidate.category.in_(categories),
            RecommendationCandidate.embedding.isnot(None),
        )
    )
    if existing_ids:
        query = query.filter(RecommendationCandidate.open_library_id.notin_(existing_ids))
    rows = query.order_by(distance.asc()).limit(limit).all()

    return [
        (
            Candidate(
                open_library_id=row.open_library_id,
                title=row.title,
                author=row.author,
                cover_url=row.cover_url,
                description=row.description,
                embedding=row.embedding,
            ),
            1 - dist,
        )
        for row, dist in rows
    ]
