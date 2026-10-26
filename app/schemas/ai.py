"""Pydantic schemas for Gemini AI Discovery and Ask features."""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AiStatusResponse(BaseModel):
    """Public status endpoint response."""

    enabled: bool
    model: str


class DiscoverRequest(BaseModel):
    """User request for natural language discovery."""

    prompt: str = Field(
        ...,
        min_length=3,
        max_length=500,
        description="Natural language description of desired movies (3 to 500 characters).",
    )


class ParsedPreferences(BaseModel):
    """Structured preferences parsed by Gemini from user discovery prompt."""

    include_genres: List[str] = Field(
        default_factory=list,
        description="MovieLens genres to include (e.g. Action, Sci-Fi, Comedy).",
    )
    exclude_genres: List[str] = Field(
        default_factory=list,
        description="MovieLens genres to exclude entirely.",
    )
    reference_titles: List[str] = Field(
        default_factory=list,
        max_length=3,
        description="Specific movie titles mentioned by the user as reference points (max 3, <=120 chars each).",
    )
    mood_terms: List[str] = Field(
        default_factory=list,
        max_length=6,
        description="Mood descriptors requested (e.g. heartwarming, dark, whimsical).",
    )
    theme_terms: List[str] = Field(
        default_factory=list,
        max_length=6,
        description="Theme descriptors requested (e.g. time travel, redemption).",
    )
    year_min: Optional[int] = Field(
        default=None,
        description="Minimum release year (1880 to current year+1).",
    )
    year_max: Optional[int] = Field(
        default=None,
        description="Maximum release year (1880 to current year+1).",
    )
    recency: Literal["recent", "classic", "any"] = Field(
        default="any",
        description="Recency preference if user asked for recent or classic films.",
    )
    sort: Literal["relevance", "most_rated", "highest_rated"] = Field(
        default="relevance",
        description="Requested sort preference.",
    )
    notes_unsupported: List[str] = Field(
        default_factory=list,
        description="Things the user requested that the catalogue lacks data for (e.g. cast, director, streaming, runtime).",
    )

    @field_validator("year_min", "year_max", mode="before")
    @classmethod
    def clamp_year(cls, v: Any) -> Optional[int]:
        if v is not None:
            try:
                iv = int(v)
                if iv < 1880:
                    return 1880
                if iv > 2030:
                    return 2030
                return iv
            except (ValueError, TypeError):
                return None
        return v

    @field_validator("reference_titles", mode="before")
    @classmethod
    def clamp_ref_titles(cls, v: Any) -> List[str]:
        if isinstance(v, list):
            return [str(t)[:120].strip() for t in v if t and str(t).strip()][:3]
        return v


class DiscoverMovieResult(BaseModel):
    """A real movie record returned by discovery or ask pipeline."""

    movie_id: int
    movie_lens_id: Optional[int] = None
    title: str
    genres: Optional[str] = None
    average_rating: Optional[float] = 0.0
    num_ratings: Optional[int] = 0
    score: float
    score_breakdown: Optional[Dict[str, float]] = None
    reasons: List[str] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class DiscoverResponse(BaseModel):
    """Response returned by /ai/discover."""

    results: List[DiscoverMovieResult]
    interpreted: ParsedPreferences
    unverified: List[str] = Field(
        default_factory=list,
        description="Mood/theme terms and unsupported items not verifiable from catalogue data.",
    )
    unresolved_references: List[str] = Field(
        default_factory=list,
        description="Titles requested as reference that could not be found in catalogue.",
    )
    message: Optional[str] = None
    relaxed: List[str] = Field(
        default_factory=list,
        description="Deterministic filter relaxations applied if strict criteria returned no results.",
    )


class AskHistoryItem(BaseModel):
    """One turn of chat history in /ai/ask."""

    role: Literal["user", "assistant"]
    text: str = Field(..., max_length=500)


class AskRequest(BaseModel):
    """User request for movie Q&A."""

    question: str = Field(..., min_length=3, max_length=500)
    movie_id: Optional[int] = None
    history: List[AskHistoryItem] = Field(default_factory=list, max_length=6)


class AskAnswer(BaseModel):
    """Structured output expected from Gemini model for Ask questions."""

    answer: str = Field(..., max_length=1200)
    catalogue_facts: List[str] = Field(
        default_factory=list,
        description="Factual statements derived strictly from catalogue data (title, year, genres, rating).",
    )
    interpretation: List[str] = Field(
        default_factory=list,
        description="Subjective interpretations or qualitative statements clearly labelled as such.",
    )
    cannot_verify: List[str] = Field(
        default_factory=list,
        description="Attributes requested (e.g. plot, cast, age rating, streaming) that cannot be verified.",
    )
    movie_ids: List[int] = Field(
        default_factory=list,
        max_length=5,
        description="Internal IDs of recommended candidate movies, chosen strictly from candidate set.",
    )


class AskResponse(BaseModel):
    """Final grounded response returned by /ai/ask to the client."""

    answer: str
    catalogue_facts: List[str]
    interpretation: List[str]
    cannot_verify: List[str]
    movie_ids: List[int]
    movies: List[DiscoverMovieResult] = Field(
        default_factory=list,
        description="Hydrated movie cards for verified candidate IDs.",
    )
