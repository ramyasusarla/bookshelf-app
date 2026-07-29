from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.embeddings import cosine_similarity
from app.models import Category
from app.recommendations import compute_taste_vector, get_candidate_pool, refresh_candidates
from app.schemas import RecommendationOut, RecommendationsResponse

router = APIRouter()

TOP_N = 3


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
) -> RecommendationsResponse:
    taste_vector = await compute_taste_vector(db, category)
    if taste_vector is None:
        scope = f"the {category.value} genre" if category is not None else "your library"
        return RecommendationsResponse(
            recommendations=[],
            message=f"Rate at least one book 7 or higher in {scope} to get recommendations.",
        )

    pool = await get_candidate_pool(db, category)
    scored = sorted(
        ((c, cosine_similarity(taste_vector, c.embedding)) for c in pool),
        key=lambda pair: pair[1],
        reverse=True,
    )

    return RecommendationsResponse(
        recommendations=[
            RecommendationOut(
                title=c.title,
                author=c.author,
                cover_url=c.cover_url,
                description=c.description,
                open_library_id=c.open_library_id,
                similarity=round(score, 4),
            )
            for c, score in scored[:TOP_N]
        ]
    )


@router.post("/recommendations/refresh")
async def refresh_recommendations(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
) -> dict[str, list[str]]:
    refreshed = await refresh_candidates(db, category)
    return {"refreshed": [c.value for c in refreshed]}
