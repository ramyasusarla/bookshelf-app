from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import Category, User
from app.recommendations import compute_taste_vector, get_top_candidates, refresh_candidates
from app.schemas import RecommendationOut, RecommendationsResponse

router = APIRouter()

TOP_N = 3


@router.get("/recommendations", response_model=RecommendationsResponse)
async def get_recommendations(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RecommendationsResponse:
    taste_vector = await compute_taste_vector(db, current_user.id, category)
    if taste_vector is None:
        scope = f"the {category.value} genre" if category is not None else "your library"
        return RecommendationsResponse(
            recommendations=[],
            message=f"Rate at least one book 7 or higher in {scope} to get recommendations.",
        )

    scored = await get_top_candidates(db, current_user.id, category, taste_vector, TOP_N)

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
            for c, score in scored
        ]
    )


@router.post("/recommendations/refresh")
async def refresh_recommendations(
    category: Category | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, list[str]]:
    # current_user isn't used directly — the candidate cache this refreshes
    # is global, not per-user — but this still costs real OpenAI calls, so
    # it's gated behind auth like every other route rather than left public.
    refreshed = await refresh_candidates(db, category)
    return {"refreshed": [c.value for c in refreshed]}
