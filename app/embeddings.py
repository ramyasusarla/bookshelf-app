import math
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Explicit path: app/.env doesn't live in an ancestor of the process's cwd,
# so load_dotenv()'s default upward search wouldn't find it.
load_dotenv(Path(__file__).parent / ".env")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
EMBEDDINGS_URL = "https://api.openai.com/v1/embeddings"
EMBEDDING_MODEL = "text-embedding-3-small"

# OpenAI accepts a list `input`, so N texts can be embedded in one HTTP call
# instead of N. Chunked defensively in case a caller ever hands over more
# texts than reasonable for one request body.
EMBEDDINGS_BATCH_CHUNK_SIZE = 100

# In-process counters for embedding cache effectiveness — incremented by
# callers (app/recommendations.py) at the point they decide "reuse a stored
# embedding" (hit) vs "this needs a new OpenAI call" (miss). Exposed via
# GET /internal/cache-stats so a real, measurable hit-rate can be reported
# instead of an estimate.
_cache_hits = 0
_cache_misses = 0


def record_cache_hit(count: int = 1) -> None:
    global _cache_hits
    _cache_hits += count


def record_cache_miss(count: int = 1) -> None:
    global _cache_misses
    _cache_misses += count


def get_embedding_cache_stats() -> dict:
    total = _cache_hits + _cache_misses
    return {
        "embeddings_served_from_cache": _cache_hits,
        "embeddings_generated": _cache_misses,
        "hit_rate": round(_cache_hits / total, 4) if total else None,
    }


async def generate_embedding(text: str) -> list[float]:
    return (await generate_embeddings_batch([text]))[0]


async def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Embed multiple texts in as few OpenAI calls as possible (one per
    EMBEDDINGS_BATCH_CHUNK_SIZE-sized chunk) instead of one call per text."""
    if not texts:
        return []
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set (expected in app/.env)")

    embeddings: list[list[float]] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        for start in range(0, len(texts), EMBEDDINGS_BATCH_CHUNK_SIZE):
            chunk = texts[start : start + EMBEDDINGS_BATCH_CHUNK_SIZE]
            response = await client.post(
                EMBEDDINGS_URL,
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
                json={"model": EMBEDDING_MODEL, "input": chunk},
            )
            response.raise_for_status()
            data = response.json()
            # The API documents but doesn't strictly guarantee response order
            # matches input order for batched requests — sort by the returned
            # "index" defensively rather than trusting list order.
            ordered = sorted(data["data"], key=lambda item: item["index"])
            embeddings.extend(item["embedding"] for item in ordered)
    return embeddings


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def average_vectors(vectors: list[list[float]]) -> list[float] | None:
    if not vectors:
        return None
    length = len(vectors[0])
    sums = [0.0] * length
    for vec in vectors:
        for i, value in enumerate(vec):
            sums[i] += value
    return [s / len(vectors) for s in sums]
