from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud, models
from app.schemas.interaction import Interaction, InteractionCreate

router = APIRouter()


@router.post(
    "/", response_model=Optional[Interaction], status_code=status.HTTP_201_CREATED
)
async def log_user_interaction(
    interaction_in: InteractionCreate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Log an interaction event (VIEW, RATE, REVIEW, WATCHLIST_ADD, WATCHLIST_REMOVE)
    with a server timestamp. Used for telemetry and future sequential model retraining.
    """
    movie = await crud.movie.get(db, id=interaction_in.movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie with ID {interaction_in.movie_id} not found.",
        )

    interaction = await crud.interaction.log_interaction(
        db,
        user_id=current_user.id,
        movie_id=interaction_in.movie_id,
        event_type=interaction_in.event_type,
    )

    return Interaction(
        id=interaction.id,
        user_id=interaction.user_id,
        movie_id=interaction.movie_id,
        event_type=interaction.event_type,
        created_at=interaction.created_at,
        movie_title=movie.title,
    )
