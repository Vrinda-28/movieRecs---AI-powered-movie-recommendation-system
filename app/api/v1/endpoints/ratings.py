import time
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud, models
from app.schemas.rating import Rating, RatingCreate

router = APIRouter()


@router.post("/", response_model=Rating, status_code=status.HTTP_201_CREATED)
async def create_rating(
    *,
    db: AsyncSession = Depends(deps.get_db),
    rating_in: RatingCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Create a new rating for a movie by the current user.
    If the user has already rated this movie, the rating and timestamp are updated in place.
    Logs RATE interaction event.
    """
    movie = await crud.movie.get(db, id=rating_in.movie_id)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail=f"Movie with ID {rating_in.movie_id} not found. Cannot add rating.",
        )

    # Use client timestamp if valid historical timestamp, else server time
    effective_ts = (
        rating_in.timestamp
        if (rating_in.timestamp and rating_in.timestamp > 0)
        else int(time.time())
    )
    rating_in.timestamp = effective_ts

    existing_rating = await crud.rating.get_by_user_and_movie(
        db, user_id=current_user.id, movie_id=rating_in.movie_id
    )
    if existing_rating:
        updated_rating = await crud.rating.update(
            db,
            db_obj=existing_rating,
            obj_in={
                "rating": rating_in.rating,
                "timestamp": effective_ts,
            },
        )
        await crud.interaction.log_interaction(
            db,
            user_id=current_user.id,
            movie_id=rating_in.movie_id,
            event_type="RATE",
        )
        return updated_rating

    rating = await crud.rating.create_with_owner(
        db=db, obj_in=rating_in, user_id=current_user.id
    )

    await crud.interaction.log_interaction(
        db,
        user_id=current_user.id,
        movie_id=rating_in.movie_id,
        event_type="RATE",
    )

    return rating


@router.get("/user/me", response_model=List[Rating])
async def read_my_ratings(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Get ratings submitted by the current user.
    """
    ratings = await crud.rating.get_ratings_by_user(
        db, user_id=current_user.id, skip=skip, limit=limit
    )
    return ratings


@router.get("/user/{user_id}", response_model=List[Rating])
async def read_user_ratings(
    user_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 100,
):
    """
    Get ratings for a specific user. Normal users can only view their own ratings; admins can view any.
    """
    if current_user.id != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions to access another user's ratings",
        )

    user = await crud.user.get(db, id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    ratings = await crud.rating.get_ratings_by_user(
        db, user_id=user_id, skip=skip, limit=limit
    )
    return ratings
