# Bookshelf

A personal book-tracking app — think a lightweight, personal Goodreads — with a comparison-based ranking system (inspired by Beli) instead of static star ratings, plus AI-powered recommendations.

## Why this exists

Most "track your books" side projects are CRUD wrappers around a database. This one tries to solve two harder problems instead:

1. **People are bad at giving consistent absolute ratings, but good at relative comparisons.** Instead of "rate this book 1-5 stars," the app has you bucket a book into a coarse tier (didn't like / alright / liked it), then places it precisely within that tier using a binary-search-style sequence of pairwise comparisons ("which did you like more?"). This gives a much more consistent, meaningful ranking than static stars, at the cost of `O(log n)` comparisons per book instead of one static input.
2. **Recommendations should work on meaning, not keywords.** A book whose description says "a warm-hearted small-town detective story following a determined amateur sleuth" should surface for someone who loved a "cozy mystery with a strong female lead" — zero shared words, same meaning. This is powered by OpenAI embeddings and cosine similarity between a taste vector (built from your highly-rated books) and each candidate's description, not text matching.

## Tech stack

**Backend:** FastAPI, SQLAlchemy + Postgres (pgvector), Clerk (auth), OpenAI embeddings API, Open Library API (search + subjects)
**Frontend:** React + TypeScript, TanStack Query, Clerk

### Why these choices
- **Postgres + pgvector over SQLite** — SQLite worked fine for a single-user local project (swappable via one connection string, since SQLAlchemy abstracts the engine), but a deployed multi-user app needs a real networked database, not a single file. pgvector additionally moves similarity search into the database itself (an indexed `ORDER BY embedding <=> taste_vector` query) instead of pulling every embedding into Python — see "Embedding storage" below.
- **Clerk over hand-rolled auth** — session/JWT handling, password resets, and sign-in UI are exactly the kind of thing not worth re-implementing for a personal project; Clerk's React components (`<SignedIn>`, `<SignInButton>`, `<UserButton>`) and FastAPI-side JWT verification (via its public JWKS) cover this with minimal integration code.
- **Open Library over Goodreads** — Goodreads closed its API to new developers in 2020. Open Library needs no API key and covers search, cover art, descriptions, and (loosely) subject/genre data.
- **TanStack Query over a general state manager (e.g. Redux) or a server cache (e.g. Redis)** — the actual problem to solve was "avoid redundant fetches, keep the UI in sync with the server." TanStack Query solves this entirely client-side with built-in caching and invalidation; Redis would have added a whole separate service for a single-user app with no real payoff.
- **OpenAI embeddings over TF-IDF** — TF-IDF is word-frequency matching with no concept of meaning; it can't do the "no shared words, same meaning" matching that's the actual point of this feature. Cost is negligible at this scale (fractions of a cent per call), and embeddings are cached and batched (see "Embedding caching" below) to keep it that way.

## Core features

- **Library management** — search Open Library (type-as-you-go, 150ms debounced) or enter a book manually; track status (bookmarked / reading / read).
- **Comparison-based ranking** — books transition to "read" only once fully ranked. Ranking assigns a tier, then (if other books already exist in that tier) runs a binary-search sequence of pairwise comparisons to find the book's exact position. Tier boundaries are computed dynamically from tier counts, not hardcoded ranges, so they scale with library size. Final `rank_position` is category-wide and maps to a 1-10 score via tier-scoped linear interpolation.
- **Recommendations** — suggests books you haven't read yet, both overall and per-genre. Builds a "taste vector" by averaging embeddings of your highly-rated (≥7) books, pulls unread candidates from Open Library's Subjects API per genre, and ranks candidates by similarity to your taste vector.

## Architecture notes

- `Book` (catalog data: title, author, cover, description, embedding, category) and `RecommendationCandidate` (the recommendation candidate-pool cache) are global/shared across every user — not scoped to one — since book metadata and a genre's candidate pool don't vary per user. `User`, `UserBook` (a user's personal relationship to a book: status, tier, rank_position, rating, dates), and `RankingSession` are scoped by `user_id`.
- The backend proxies all Open Library calls rather than letting the frontend call it directly — Open Library doesn't support CORS, so browser-side calls would be blocked outright.
- **Auth:** Clerk issues a session JWT to the frontend (`@clerk/clerk-react`); every user-scoped route verifies it server-side against Clerk's public JWKS (`app/auth.py`) and resolves/creates the corresponding local `User` row on first sight. `Book`/`RecommendationCandidate` routes stay unauthenticated (`/books/search`) or auth-gated but not user-scoped (`/recommendations/refresh`, since it only warms a shared cache).
- **Data normalization (`app/normalization.py`):** Open Library's metadata is inconsistent — descriptions are sometimes missing, author names show up as "Last, First", multi-author strings, or lists of `{name: ...}` dicts, and subject tags are free-text and inconsistently cased. `normalize_book()` is the single seam between a raw Open Library response and the DB: it standardizes author formatting, normalizes/dedupes subject tags into a small controlled vocabulary, and — critically — returns `embedding_text=None` (not a placeholder string) when there's no description, so callers skip embedding generation entirely rather than embedding weak `"title by author"` text. Covered by unit tests in `tests/test_normalization.py`.

**Embedding storage:** each `Book`/`RecommendationCandidate` row has an `embedding` column — a pgvector `vector(1536)` (from `text-embedding-3-small`), enabling real DB-side similarity search instead of pulling every embedding into Python. Embeddings are generated lazily — a book only gets embedded the first time it's needed for a taste-vector calculation (i.e., the first time it's rated 7 or higher) — and only when a description exists (see normalization above); once computed, it's cached on the row permanently, since the source text never changes.

**Embedding caching / cost control (`app/embeddings.py`):** before generating any embedding, existing call sites check whether one's already stored (keyed by the book's stable Open Library ID, via the `Book`/`RecommendationCandidate` row itself). When multiple books need embedding at once — a genre's candidate pool, or several newly-rated books — they're embedded in a single batched OpenAI call (`generate_embeddings_batch`, chunked at 100 texts/request) instead of one call per book. An in-process hit/miss counter is exposed at `GET /internal/cache-stats` so the cache-hit-rate is a real measured number, not an estimate — hit it before/after a `POST /recommendations/refresh` to see it move.

**Caching strategy for recommendations:** candidate books for the "unread recommendations" feature come from Open Library's Subjects API, one genre at a time. Fetching descriptions and generating embeddings for ~20 candidates per genre is comparatively expensive (an external Open Library call per candidate, capped at 5 concurrent requests to avoid getting rate-limited, plus one batched OpenAI call for the whole genre), so this candidate pool — book metadata plus its embedding — is persisted to `recommendation_candidates`, keyed by genre, after the first fetch. Subsequent requests for the same genre read straight from the database instead of re-fetching and re-embedding, and the cache survives server restarts. An explicit `POST /recommendations/refresh` endpoint (optionally scoped to one genre) forces a re-fetch when a stale pool needs updating. Final ranking against a user's taste vector is a single pgvector `ORDER BY embedding <=> taste_vector LIMIT N` query, not a Python loop. The user's taste vector (the average embedding of their own highly-rated books) is cheap to compute locally and is *not* cached — it's recalculated on every request so newly rated books immediately affect recommendations.

## Known limitations / roadmap

Being upfront about what's incomplete, rather than pretending otherwise:

- **A cold cache is still slow, and Open Library's rate limits are undocumented.** The candidate pool is persisted (see above), so this cost is only paid once per genre rather than on every request — but the *first* request for an uncached genre still makes up to 20 external round trips, and an "overall" recommendation request touching all 10 genres at once can take 30-60+ seconds cold. Requests are capped at 5 concurrent specifically because an uncapped burst was observed getting the server's IP temporarily blocked by Open Library during development — this is a real, reproduced failure mode, not a hypothetical one.
- **Manual book entry has no de-duplication safeguard.** Books added via Open Library search get a uniqueness constraint on `open_library_id`; manually entered books (no Open Library match) don't get the same protection against near-duplicate entries.
- **No free-text semantic search yet.** Recommendations work off a taste vector built from your ratings, but there's no endpoint that takes an arbitrary query ("cozy mystery with a strong female lead") and embeds it directly — that's a natural extension of the existing embedding infrastructure, just not built yet.
- **Genre-to-Open-Library-subject mapping is a hardcoded, imperfect heuristic** — Open Library subjects are free-text and messy; the mapping is a best-effort guess, not a guaranteed clean match.
- **Multi-edition dedup (`pick_best_edition()` in `app/normalization.py`) is implemented and unit-tested but not wired to a live Open Library call** — no current call site fetches per-work edition lists (that's an extra HTTP call per candidate against an already rate-limit-sensitive budget), so it's exercised by tests, not production traffic, today.

## Running locally

Requires Docker (for local Postgres+pgvector — SQLite can't be used anymore since pgvector needs a real Postgres `vector` column type) and a free [Clerk](https://clerk.com) application (dashboard → API Keys, for the publishable key + Frontend API URL).

```bash
# Start local Postgres (pgvector-enabled) — from the project root
docker compose up -d

# Backend
uv sync
echo 'OPENAI_API_KEY=sk-...' >> app/.env
echo 'CLERK_ISSUER=https://your-app-name.clerk.accounts.dev' >> app/.env
uv run alembic upgrade head   # creates the schema (incl. the vector extension)
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
echo 'VITE_CLERK_PUBLISHABLE_KEY=pk_test_...' >> .env.local
npm run dev
```

Backend docs (interactive Swagger UI): `http://localhost:8000/docs`
Frontend: `http://localhost:5173`

Run the backend test suite with `uv run pytest`.
