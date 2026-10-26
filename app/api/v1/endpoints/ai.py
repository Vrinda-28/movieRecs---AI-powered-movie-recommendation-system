"""FastAPI endpoint router for Groq AI features (/api/v1/ai)."""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.db import models
from app.schemas.ai import (
    AiStatusResponse,
    AskRequest,
    AskResponse,
    DiscoverRequest,
    DiscoverResponse,
)
from app.services.ai.ask import ask_about_movie
from app.services.ai.discovery import discover_movies
from app.services.ai.groq_client import (
    AiAuthFailedError,
    AiBaseError,
    AiNotConfiguredError,
    GroqClient,
    get_groq,
)
from app.services.ai.guards import rate_limiter

# Aliases for backward compatibility
GeminiClient = GroqClient
get_gemini = get_groq

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/status", response_model=AiStatusResponse)
async def get_ai_status(
    ai_client: GroqClient = Depends(get_groq),
) -> AiStatusResponse:
    """Public status endpoint indicating whether AI features are enabled and configured.

    Never exposes secrets or API keys.
    """
    return AiStatusResponse(
        enabled=ai_client.is_configured,
        model=ai_client.model,
    )


@router.post("/discover", response_model=DiscoverResponse)
async def discover_endpoint(
    request: DiscoverRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    gemini_client: GeminiClient = Depends(get_gemini),
) -> DiscoverResponse:
    """Natural-language movie discovery endpoint.

    Requires an active authenticated user.
    """
    if not gemini_client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ai_not_configured",
        )

    # Per-user sliding-window rate limit
    rate_limiter.check(current_user.id)

    try:
        response = await discover_movies(
            db=db,
            gemini_client=gemini_client,
            prompt=request.prompt,
            user=current_user,
        )
        return response
    except AiBaseError as exc:
        safe_detail = (
            "ai_auth_failed" if isinstance(exc, AiAuthFailedError) else exc.detail
        )
        raise HTTPException(status_code=exc.status_code, detail=safe_detail)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in /discover: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ai_bad_response",
        )


@router.post("/ask", response_model=AskResponse)
async def ask_endpoint(
    request: AskRequest,
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_active_user),
    gemini_client: GeminiClient = Depends(get_gemini),
) -> AskResponse:
    """Grounded movie Q&A endpoint ('Ask About Movies').

    Requires an active authenticated user.
    """
    if not gemini_client.is_configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ai_not_configured",
        )

    # Per-user sliding-window rate limit
    rate_limiter.check(current_user.id)

    try:
        response = await ask_about_movie(
            db=db,
            gemini_client=gemini_client,
            question=request.question,
            movie_id=request.movie_id,
            history=request.history,
            user=current_user,
        )
        return response
    except AiBaseError as exc:
        safe_detail = (
            "ai_auth_failed" if isinstance(exc, AiAuthFailedError) else exc.detail
        )
        raise HTTPException(status_code=exc.status_code, detail=safe_detail)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Unexpected error in /ask: {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="ai_bad_response",
        )
