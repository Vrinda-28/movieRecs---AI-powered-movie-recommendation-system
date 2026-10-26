from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud, models
from app.schemas.review import Review, ReviewCreate, ReviewUpdate

router = APIRouter()


@router.post("/", response_model=Review, status_code=status.HTTP_201_CREATED)
async def create_review(
    *,
    db: AsyncSession = Depends(deps.get_db),
    review_in: ReviewCreate,
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Create a review for a movie.
    Enforces authentication, trimmed text validation (1-2000 chars),
    and one review per user per movie (409 Conflict if already reviewed).
    Logs REVIEW interaction event with server timestamp.
    """
    cleaned_text = review_in.text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Review text cannot be empty or only whitespace.",
        )
    if len(cleaned_text) > 2000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Review text cannot exceed 2000 characters.",
        )

    # Check movie exists
    movie = await crud.movie.get(db, id=review_in.movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie with ID {review_in.movie_id} not found.",
        )

    # Enforce one review per user per movie
    existing = await crud.review.get_by_user_and_movie(
        db, user_id=current_user.id, movie_id=review_in.movie_id
    )
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You have already submitted a review for this movie. Update your existing review instead.",
        )

    review_in.text = cleaned_text
    created_review = await crud.review.create_with_owner(
        db, obj_in=review_in, user_id=current_user.id
    )

    # Log interaction event (sequential behavior modeling)
    await crud.interaction.log_interaction(
        db,
        user_id=current_user.id,
        movie_id=review_in.movie_id,
        event_type="REVIEW",
    )

    # Fetch user's rating for display if present
    user_rating_obj = await crud.rating.get_by_user_and_movie(
        db, user_id=current_user.id, movie_id=review_in.movie_id
    )

    return Review(
        id=created_review.id,
        user_id=created_review.user_id,
        movie_id=created_review.movie_id,
        text=created_review.text,
        created_at=created_review.created_at,
        updated_at=created_review.updated_at,
        user_email=current_user.email,
        movie_title=movie.title,
        user_rating=user_rating_obj.rating if user_rating_obj else None,
    )


@router.get("/movies/{movie_id}", response_model=List[Review])
async def get_movie_reviews(
    movie_id: int,
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 50,
):
    """
    Retrieve all reviews for a specific movie in reverse chronological order.
    Public endpoint.
    """
    movie = await crud.movie.get(db, id=movie_id)
    if not movie:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Movie with ID {movie_id} not found.",
        )

    reviews_orm = await crud.review.get_multi_by_movie(
        db, movie_id=movie_id, skip=skip, limit=limit
    )

    results = []
    for r in reviews_orm:
        user_rating = await crud.rating.get_by_user_and_movie(
            db, user_id=r.user_id, movie_id=movie_id
        )
        results.append(
            Review(
                id=r.id,
                user_id=r.user_id,
                movie_id=r.movie_id,
                text=r.text,
                created_at=r.created_at,
                updated_at=r.updated_at,
                user_email=r.user.email if r.user else f"user_{r.user_id}",
                movie_title=movie.title,
                user_rating=user_rating.rating if user_rating else None,
            )
        )
    return results


@router.put("/{review_id}", response_model=Review)
async def update_review(
    review_id: int,
    review_in: ReviewUpdate,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Update an existing review. Ownership enforced: only the author can edit.
    """
    review_orm = await crud.review.get(db, id=review_id)
    if not review_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    if review_orm.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to edit another user's review.",
        )

    cleaned_text = review_in.text.strip()
    if not cleaned_text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Review text cannot be empty.",
        )

    updated_orm = await crud.review.update(
        db, db_obj=review_orm, obj_in={"text": cleaned_text}
    )

    movie = await crud.movie.get(db, id=updated_orm.movie_id)
    user_rating_obj = await crud.rating.get_by_user_and_movie(
        db, user_id=current_user.id, movie_id=updated_orm.movie_id
    )

    return Review(
        id=updated_orm.id,
        user_id=updated_orm.user_id,
        movie_id=updated_orm.movie_id,
        text=updated_orm.text,
        created_at=updated_orm.created_at,
        updated_at=updated_orm.updated_at,
        user_email=current_user.email,
        movie_title=movie.title if movie else None,
        user_rating=user_rating_obj.rating if user_rating_obj else None,
    )


@router.delete("/{review_id}", status_code=status.HTTP_200_OK)
async def delete_review(
    review_id: int,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Delete a review. Author or admin only.
    """
    review_orm = await crud.review.get(db, id=review_id)
    if not review_orm:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Review not found.",
        )

    if review_orm.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this review.",
        )

    await crud.review.remove(db, id=review_id)
    return {"message": "Review deleted successfully", "id": review_id}
