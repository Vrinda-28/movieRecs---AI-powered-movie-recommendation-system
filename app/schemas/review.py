from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ReviewBase(BaseModel):
    text: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Review text between 1 and 2000 characters",
    )


class ReviewCreate(ReviewBase):
    movie_id: int


class ReviewUpdate(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=2000, description="Updated review text"
    )


class ReviewInDBBase(ReviewBase):
    id: int
    user_id: int
    movie_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class Review(ReviewInDBBase):
    user_email: Optional[str] = None
    movie_title: Optional[str] = None
    user_rating: Optional[float] = None
