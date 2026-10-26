from datetime import datetime
from typing import Optional

from pydantic import BaseModel

from app.schemas.movie import MovieInList


class WatchlistBase(BaseModel):
    movie_id: int


class WatchlistCreate(WatchlistBase):
    pass


class WatchlistItem(BaseModel):
    id: int
    user_id: int
    movie_id: int
    created_at: datetime
    movie: Optional[MovieInList] = None

    class Config:
        from_attributes = True
