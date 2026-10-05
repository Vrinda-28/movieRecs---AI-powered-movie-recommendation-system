from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.db import crud
from app.schemas.movie import Movie, MovieCreate, MovieInList, MovieUpdate

router = APIRouter()


from app.db import models


@router.post("/", response_model=Movie, status_code=status.HTTP_201_CREATED)
async def create_movie(
    *,
    db: AsyncSession = Depends(deps.get_db),
    movie_in: MovieCreate,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """
    Add a new movie to the database. Admin only.
    'movie_lens_id' is optional. Internal 'id' is auto-generated.
    """

    if movie_in.movie_lens_id is not None:
        existing_by_lens_id = await crud.movie.get_by_movie_lens_id(
            db, movie_lens_id=movie_in.movie_lens_id
        )
        if existing_by_lens_id:
            raise HTTPException(
                status_code=400,
                detail=f"Movie with MovieLens ID {movie_in.movie_lens_id} already exists with internal ID {existing_by_lens_id.id}.",
            )

    created_movie_orm = await crud.movie.create(db=db, obj_in=movie_in)

    return await crud.movie.get(db, id=created_movie_orm.id)


@router.delete("/{movie_id}", status_code=status.HTTP_200_OK)
async def delete_movie(
    *,
    db: AsyncSession = Depends(deps.get_db),
    movie_id: int,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """
    Delete a movie by its internal database ID. Admin only.
    """
    movie = await crud.movie.get(db, id=movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    await crud.movie.remove(db, id=movie_id)
    return {"message": f"Movie {movie_id} deleted successfully", "id": movie_id}



@router.get("/{movie_id}", response_model=Movie)
async def read_movie(
    *,
    db: AsyncSession = Depends(deps.get_db),
    movie_id: int,
):
    """
    Get a movie by its internal database ID, including ratings and aggregates.
    """
    movie_with_details = await crud.movie.get(db, id=movie_id)
    if not movie_with_details:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie_with_details


@router.get("/", response_model=List[MovieInList])
async def read_movies(
    db: AsyncSession = Depends(deps.get_db),
    skip: int = 0,
    limit: int = 20,
    search: Optional[str] = None,
    genres: Optional[str] = Query(
        None,
        description="Comma-separated list of genres to filter by (e.g., Action,Comedy)",
    ),
):
    """
    Retrieve a list of movies with summary rating information.
    Supports searching by title and filtering by genres.
    For genre filtering, provide a comma-separated string. Movies matching ALL provided genres will be returned.
    """
    parsed_genres: Optional[List[str]] = None
    if genres:
        parsed_genres = [genre.strip() for genre in genres.split(",") if genre.strip()]
        if not parsed_genres:
            parsed_genres = None

    movies = await crud.movie.get_multi_with_rating_summary(
        db, skip=skip, limit=limit, search_term=search, filter_genres=parsed_genres
    )
    return movies
