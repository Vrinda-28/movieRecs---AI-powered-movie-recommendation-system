from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud, models
from app.schemas.movie import MovieInList
from app.schemas.watchlist import WatchlistItem

router = APIRouter()


@router.post(
    "/{movie_id}", response_model=WatchlistItem, status_code=status.HTTP_201_CREATED
)
async def add_to_watchlist(
    movie_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Add a movie to the user's watchlist.
    Idempotent: if already present, returns the existing entry.
    Logs WATCHLIST_ADD interaction event.
    """
    movie = await crud.movie.get(db, id=movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie with ID {movie_id} not found.",
        )

    item = await crud.watchlist.add_to_watchlist(
        db, user_id=current_user.id, movie_id=movie_id
    )

    # Log interaction event
    await crud.interaction.log_interaction(
        db,
        user_id=current_user.id,
        movie_id=movie_id,
        event_type="WATCHLIST_ADD",
    )

    return WatchlistItem(
        id=item.id,
        user_id=item.user_id,
        movie_id=item.movie_id,
        created_at=item.created_at,
        movie=MovieInList.model_validate(movie),
    )


@router.delete("/{movie_id}", status_code=status.HTTP_200_OK)
async def remove_from_watchlist(
    movie_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Remove a movie from the user's watchlist.
    Logs WATCHLIST_REMOVE interaction event.
    """
    removed = await crud.watchlist.remove_from_watchlist(
        db, user_id=current_user.id, movie_id=movie_id
    )

    if removed:
        await crud.interaction.log_interaction(
            db,
            user_id=current_user.id,
            movie_id=movie_id,
            event_type="WATCHLIST_REMOVE",
        )

    return {
        "message": f"Movie {movie_id} removed from watchlist",
        "movie_id": movie_id,
        "removed": removed,
    }


@router.get("/", response_model=List[WatchlistItem])
async def get_my_watchlist(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
):
    """
    Retrieve current user's watchlist with pagination.
    """
    items = await crud.watchlist.get_user_watchlist(
        db, user_id=current_user.id, skip=skip, limit=limit
    )

    results = []
    for item in items:
        movie_schema = MovieInList.model_validate(item.movie) if item.movie else None
        results.append(
            WatchlistItem(
                id=item.id,
                user_id=item.user_id,
                movie_id=item.movie_id,
                created_at=item.created_at,
                movie=movie_schema,
            )
        )
    return results


@router.get("/check/{movie_id}")
async def check_watchlist_status(
    movie_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Check if a specific movie is in current user's watchlist.
    """
    item = await crud.watchlist.get_by_user_and_movie(
        db, user_id=current_user.id, movie_id=movie_id
    )
    return {"movie_id": movie_id, "in_watchlist": item is not None}
