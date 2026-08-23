import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.embeddings import get_embedding_cache_stats
from app.routers.books import router as books_router
from app.routers.recommendations import router as recommendations_router

# Schema is managed by Alembic now (see migrations/), not created implicitly
# at startup — run `alembic upgrade head` before starting the app.
app = FastAPI(title="Bookshelf API")

# Local dev origin is always allowed; production adds the deployed frontend's
# origin via env var so this doesn't need a code change (and redeploy) once
# the frontend's URL is known.
allowed_origins = ["http://localhost:5173"]
frontend_url = os.environ.get("FRONTEND_URL")
if frontend_url:
    allowed_origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books_router)
app.include_router(recommendations_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/internal/cache-stats")
def cache_stats() -> dict:
    """Embedding cache hit/miss counters — see app/embeddings.py. Lets a real
    cache-hit-rate number be captured (e.g. before/after a
    POST /recommendations/refresh) instead of an estimate."""
    return get_embedding_cache_stats()
