# Bookshelf

A personal book-tracking app — think a lightweight, personal Goodreads — with a comparison-based ranking system (inspired by Beli) instead of static star ratings, plus AI-powered recommendations.

## Why this exists

Most "track your books" side projects are CRUD wrappers around a database. This one tries to solve two harder problems instead:

1. **People are bad at giving consistent absolute ratings, but good at relative comparisons.** Instead of "rate this book 1-5 stars," the app has you bucket a book into a coarse tier (didn't like / alright / liked it), then places it precisely within that tier using a binary-search-style sequence of pairwise comparisons ("which did you like more?"). This gives a much more consistent, meaningful ranking than static stars, at the cost of `O(log n)` comparisons per book instead of one static input.
2. **Recommendations should work on meaning, not keywords.** A book whose description says "a warm-hearted small-town detective story following a determined amateur sleuth" should surface for someone who loved a "cozy mystery with a strong female lead" — zero shared words, same meaning. This is powered by OpenAI embeddings and cosine similarity between a taste vector (built from your highly-rated books) and each candidate's description, not text matching.

## Tech stack

**Backend:** FastAPI, SQLAlchemy + SQLite, OpenAI embeddings API, Open Library API (search + subjects)
**Frontend:** React + TypeScript, TanStack Query

### Why these choices
- **SQLite over Postgres** — zero setup for a single-user project; swappable later via one connection string change since SQLAlchemy abstracts the engine.
- **Open Library over Goodreads** — Goodreads closed its API to new developers in 2020. Open Library needs no API key and covers search, cover art, descriptions, and (loosely) subject/genre data.
- **TanStack Query over a general state manager (e.g. Redux) or a server cache (e.g. Redis)** — the actual problem to solve was "avoid redundant fetches, keep the UI in sync with the server." TanStack Query solves this entirely client-side with built-in caching and invalidation; Redis would have added a whole separate service for a single-user app with no real payoff.
- **OpenAI embeddings over TF-IDF** — TF-IDF is word-frequency matching with no concept of meaning; it can't do the "no shared words, same meaning" matching that's the actual point of this feature. Cost is negligible at this scale (fractions of a cent per call).

## Core features

- **Library management** — search Open Library (type-as-you-go, 150ms debounced) or enter a book manually; track status (bookmarked / reading / read).
- **Comparison-based ranking** — books transition to "read" only once fully ranked. Ranking assigns a tier, then (if other books already exist in that tier) runs a binary-search sequence of pairwise comparisons to find the book's exact position. Tier boundaries are computed dynamically from tier counts, not hardcoded ranges, so they scale with library size. Final `rank_position` is category-wide and maps to a 1-10 score via tier-scoped linear interpolation.
- **Recommendations** — suggests books you haven't read yet, both overall and per-genre. Builds a "taste vector" by averaging embeddings of your highly-rated (≥7) books, pulls unread candidates from Open Library's Subjects API per genre, and ranks candidates by similarity to your taste vector.

## Architecture notes

- `Book` (catalog data: title, author, cover, description, embedding, category) is separate from `UserBook` (a user's personal relationship to a book: status, tier, rank_position, rating, dates) — this avoids duplicating shared book metadata and keeps per-user state lightweight.
- The backend proxies all Open Library calls rather than letting the frontend call it directly — Open Library doesn't support CORS, so browser-side calls would be blocked outright.

**Embedding storage:** each `Book` row has an `embedding` column — a JSON-serialized list of floats (1536-dimensional, from `text-embedding-3-small`). SQLite has no native vector type, so the vector is stored as text and deserialized in Python at query time. Embeddings are generated lazily, not when a book is added — a book only gets embedded the first time it's needed for a taste-vector calculation (i.e., the first time it's rated 7 or higher), from its `description`, or a `title + author` fallback if no description is available. Once computed, it's cached on the row permanently, since the source text never changes. This is a deliberate simplification: at the scale of a personal library (tens to low hundreds of books), computing cosine similarity against every stored embedding in plain Python at request time is fast enough that a dedicated vector database (e.g. Pinecone) would be unnecessary infrastructure for the problem size.

**Caching strategy for recommendations:** candidate books for the "unread recommendations" feature come from Open Library's Subjects API, one genre at a time. Fetching descriptions and generating embeddings for ~20 candidates per genre is comparatively expensive (two external API calls per candidate — one to Open Library, one to OpenAI — capped at 5 concurrent requests to avoid getting rate-limited), so this candidate pool — book metadata plus its embedding — is persisted to a SQLite table, keyed by genre, after the first fetch. Subsequent requests for the same genre read straight from the database instead of re-fetching and re-embedding, and the cache survives server restarts. An explicit `POST /recommendations/refresh` endpoint (optionally scoped to one genre) forces a re-fetch when a stale pool needs updating. The user's "taste vector" (the average embedding of their own highly-rated books) is cheap to compute locally and is *not* cached — it's recalculated on every request so newly rated books immediately affect recommendations.

## Known limitations / roadmap

Being upfront about what's incomplete, rather than pretending otherwise:

- **A cold cache is still slow, and Open Library's rate limits are undocumented.** The candidate pool is persisted (see above), so this cost is only paid once per genre rather than on every request — but the *first* request for an uncached genre still makes up to 20 external round trips, and an "overall" recommendation request touching all 10 genres at once can take 30-60+ seconds cold. Requests are capped at 5 concurrent specifically because an uncapped burst was observed getting the server's IP temporarily blocked by Open Library during development — this is a real, reproduced failure mode, not a hypothetical one.
- **No authentication yet.** Currently single-user by design; auth is a planned addition specifically for practice with that flow.
- **Manual book entry has no de-duplication safeguard.** Books added via Open Library search get a uniqueness constraint on `open_library_id`; manually entered books (no Open Library match) don't get the same protection against near-duplicate entries.
- **No free-text semantic search yet.** Recommendations work off a taste vector built from your ratings, but there's no endpoint that takes an arbitrary query ("cozy mystery with a strong female lead") and embeds it directly — that's a natural extension of the existing embedding infrastructure, just not built yet.
- **Genre-to-Open-Library-subject mapping is a hardcoded, imperfect heuristic** — Open Library subjects are free-text and messy; the mapping is a best-effort guess, not a guaranteed clean match.

## Running locally

```bash
# Backend (from the project root)
uv sync
echo 'OPENAI_API_KEY=sk-...' > app/.env
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

Backend docs (interactive Swagger UI): `http://localhost:8000/docs`
Frontend: `http://localhost:5173`
