from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InteractionCreate(BaseModel):
    movie_id: int
    event_type: str = Field(
        ...,
        pattern="^(VIEW|RATE|REVIEW|WATCHLIST_ADD|WATCHLIST_REMOVE)$",
        description="Interaction event type: VIEW, RATE, REVIEW, WATCHLIST_ADD, or WATCHLIST_REMOVE",
    )


class Interaction(BaseModel):
    id: int
    user_id: int
    movie_id: int
    event_type: str
    created_at: datetime
    movie_title: Optional[str] = None

    class Config:
        from_attributes = True


class UserHistoryItem(BaseModel):
    event_type: str
    movie_id: int
    movie_title: Optional[str] = None
    rating: Optional[float] = None
    timestamp: datetime
