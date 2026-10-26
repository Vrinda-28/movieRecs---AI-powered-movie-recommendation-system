from datetime import datetime, timedelta, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app import schemas
from app.api import deps
from app.core.config import settings
from app.db import crud, models
from app.schemas.interaction import UserHistoryItem
from app.schemas.token import Token
from app.schemas.user import User, UserCreate
from app.security import create_access_token, verify_password

router = APIRouter()


@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register_user(
    *,
    db: AsyncSession = Depends(deps.get_db),
    user_in: UserCreate,
):
    """
    Create new user. Public registration always creates non-admin users (is_admin=False).
    """
    existing_user = await crud.user.get_by_email(db, email=user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=400,
            detail="The user with this email already exists in the system.",
        )
    # Ensure public registration never grants admin privileges
    safe_user_in = UserCreate(
        email=user_in.email,
        password=user_in.password,
        is_admin=False,
    )
    user = await crud.user.create(db=db, obj_in=safe_user_in)
    return user


@router.post("/login/token", response_model=Token)
async def login_for_access_token(
    db: AsyncSession = Depends(deps.get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
):
    """
    OAuth2 compatible token login, get an access token for future requests.
    """
    user = await crud.user.get_by_email(db, email=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get("/me", response_model=User)
async def read_users_me(
    current_user: models.User = Depends(deps.get_current_active_user),
):
    """
    Get current user profile.
    """
    return current_user


@router.get("/me/history", response_model=List[UserHistoryItem])
async def read_users_me_history(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    skip: int = 0,
    limit: int = 50,
):
    """
    Returns the user's chronological interaction and rating history.
    """
    # 1. Fetch ratings
    ratings = await crud.rating.get_ratings_by_user(
        db, user_id=current_user.id, skip=0, limit=100
    )
    # 2. Fetch logged interactions
    interactions = await crud.interaction.get_user_interactions(
        db, user_id=current_user.id, skip=0, limit=100
    )

    history_items: List[UserHistoryItem] = []

    def to_utc(dt_val):
        if dt_val is None:
            return datetime.min.replace(tzinfo=timezone.utc)
        if isinstance(dt_val, (int, float)):
            return datetime.fromtimestamp(dt_val, tz=timezone.utc)
        if dt_val.tzinfo is None:
            return dt_val.replace(tzinfo=timezone.utc)
        return dt_val

    for r in ratings:
        dt = to_utc(
            r.timestamp if isinstance(r.timestamp, (int, float)) else r.created_at
        )
        history_items.append(
            UserHistoryItem(
                event_type="RATE",
                movie_id=r.movie_id,
                movie_title=r.movie.title if r.movie else None,
                rating=r.rating,
                timestamp=dt,
            )
        )

    for i in interactions:
        dt = to_utc(i.created_at)
        history_items.append(
            UserHistoryItem(
                event_type=i.event_type,
                movie_id=i.movie_id,
                movie_title=i.movie.title if i.movie else None,
                rating=None,
                timestamp=dt,
            )
        )

    # Sort descending by timestamp
    history_items.sort(key=lambda x: x.timestamp, reverse=True)
    return history_items[skip : skip + limit]
