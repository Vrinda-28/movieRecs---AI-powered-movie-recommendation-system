from fastapi import APIRouter

from app.api.v1.endpoints import (
    admin,
    ai,
    interactions,
    movies,
    ratings,
    recommendations,
    reviews,
    users,
    watchlist,
)

api_router = APIRouter()
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(movies.router, prefix="/movies", tags=["movies"])
api_router.include_router(ratings.router, prefix="/ratings", tags=["ratings"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["reviews"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(
    interactions.router, prefix="/interactions", tags=["interactions"]
)
api_router.include_router(
    recommendations.router, prefix="/recommendations", tags=["recommendations"]
)
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
