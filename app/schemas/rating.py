from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class RatingBase(BaseModel):
    movie_id: int
    rating: float = Field(
        ..., ge=1.0, le=5.0, description="Rating score from 1.0 to 5.0"
    )
    timestamp: int


class RatingCreate(RatingBase):
    pass


class RatingUpdate(BaseModel):
    rating: Optional[float] = Field(None, ge=1.0, le=5.0)
    timestamp: Optional[int] = None


class RatingInDB(RatingBase):
    id: int
    user_id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class Rating(RatingInDB):

    pass
