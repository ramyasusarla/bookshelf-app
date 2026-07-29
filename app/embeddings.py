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


async def generate_embedding(text: str) -> list[float]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set (expected in app/.env)")
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(
            EMBEDDINGS_URL,
            headers={"Authorization": f"Bearer {OPENAI_API_KEY}"},
            json={"model": EMBEDDING_MODEL, "input": text},
        )
        response.raise_for_status()
        data = response.json()
    return data["data"][0]["embedding"]


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
