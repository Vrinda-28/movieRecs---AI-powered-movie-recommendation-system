from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud, models
from app.services.recommender.predict import (
    get_inference_trace_for_user,
    get_recommendations_for_user,
)

router = APIRouter()


@router.get("/user/me", response_model=List[Dict[str, Any]])
async def get_my_recommendations(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    exclude_watched: bool = True,
    count: int = 10,
):
    """
    Get movie recommendations for the currently authenticated user.

    Response items carry:
      - source: "gru4rec" (model-generated) | "popularity" (cold-start or backfill)
      - score: null — the BruteForceRetrieval layer returns sorted candidate indices,
                not raw dot-product scalars. Exposing score would require enabling
                return_scores=True on the retrieval layer and is a future enhancement.
                Do NOT interpret null as "low confidence"; it simply means the score
                is not available in the current model configuration.
      - is_personalized: mirrors source ("gru4rec" → True, "popularity" → False)
      - user_rating_count: number of ratings the user had at inference time,
                           useful for frontend progress messaging.
    """
    if count <= 0 or count > 50:
        count = 10

    recommendations = await get_recommendations_for_user(
        db=db,
        user=current_user,
        exclude_watched=exclude_watched,
        num_recommendations=count,
    )
    return recommendations


@router.get("/user/{user_id}", response_model=List[Dict[str, Any]])
async def get_user_recommendations(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    exclude_watched: bool = True,
    count: int = 10,
):
    """
    Get movie recommendations for a specific user ID.
    Non-admin callers can only fetch their own recommendations; admins can fetch any.
    """
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=403,
            detail="Not enough permissions to access another user's recommendations",
        )

    target_user = await crud.user.get(db, id=user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    if count <= 0 or count > 50:
        count = 10

    recommendations = await get_recommendations_for_user(
        db=db,
        user=target_user,
        exclude_watched=exclude_watched,
        num_recommendations=count,
    )
    return recommendations


@router.get("/debug/me", response_model=Dict[str, Any])
async def get_my_inference_trace(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_admin_user),
    count: int = 10,
):
    """
    Admin-only: returns the complete inference audit trace for the calling admin user.

    This endpoint is intentionally restricted to admin users.
    It reveals internal model mechanics including the raw padded input window,
    all retrieved IDs before filtering, and which IDs were removed because
    the user had already rated them.

    Regular users must never access this endpoint (403 returned by dep).
    """
    if count <= 0 or count > 50:
        count = 10

    trace = await get_inference_trace_for_user(
        db=db,
        user=current_user,
        num_recommendations=count,
    )
    return trace


@router.get("/debug/user/{user_id}", response_model=Dict[str, Any])
async def get_user_inference_trace(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_admin_user),
    count: int = 10,
):
    """
    Admin-only: returns the complete inference audit trace for any user by ID.
    Useful for demonstrating personalization differences between demo personas.
    """
    target_user = await crud.user.get(db, id=user_id)
    if not target_user:
        raise HTTPException(status_code=404, detail="Target user not found")

    if count <= 0 or count > 50:
        count = 10

    trace = await get_inference_trace_for_user(
        db=db,
        user=target_user,
        num_recommendations=count,
    )
    return trace
