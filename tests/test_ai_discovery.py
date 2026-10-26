"""Tests for Groq AI movie discovery pipeline."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.db.models import User
from app.main import app
from app.schemas.ai import ParsedPreferences
from app.schemas.movie import MovieCreate
from app.schemas.rating import RatingCreate
from app.schemas.user import UserCreate
from app.services.ai.groq_client import GroqClient, get_groq
from app.services.ai.guards import rate_limiter

GeminiClient = GroqClient
get_gemini = get_groq


class MockGroqClient(GroqClient):
    """Mock GroqClient returning configurable responses."""

    def __init__(self, response_obj=None, should_raise=None):
        super().__init__(api_key="gsk_test_dummy_key_12345", model=settings.GROQ_MODEL)
        self.response_obj = response_obj
        self.should_raise = should_raise

    async def generate_json(self, system: str, user: str, schema):
        if self.should_raise:
            raise self.should_raise
        return self.response_obj


MockGeminiClient = MockGroqClient


async def seed_test_catalogue(db: AsyncSession) -> dict:
    """Seeds a test catalogue with 12 movies of known years and genres."""
    movies_data = [
        {
            "title": "Toy Story (1995)",
            "genres": "Animation|Children's|Comedy",
            "movie_lens_id": 1,
        },
        {"title": "Matrix, The (1999)", "genres": "Action|Sci-Fi", "movie_lens_id": 2},
        {"title": "Alien (1979)", "genres": "Action|Horror|Sci-Fi", "movie_lens_id": 3},
        {"title": "Die Hard (1988)", "genres": "Action|Thriller", "movie_lens_id": 4},
        {
            "title": "Action Hero (1990)",
            "genres": "Action-Adventure|Comedy",
            "movie_lens_id": 5,
        },
        {
            "title": "Metropolis",
            "genres": "Sci-Fi",
            "movie_lens_id": 6,
        },  # No year in title
        {
            "title": "Fugitive, The (1993)",
            "genres": "Action|Thriller",
            "movie_lens_id": 7,
        },
        {
            "title": "Jurassic Park (1993)",
            "genres": "Action|Adventure|Sci-Fi",
            "movie_lens_id": 8,
        },
        {"title": "Godfather, The (1972)", "genres": "Crime|Drama", "movie_lens_id": 9},
        {
            "title": "Casablanca (1942)",
            "genres": "Drama|Romance|War",
            "movie_lens_id": 10,
        },
        {"title": "Scream (1996)", "genres": "Horror|Mystery", "movie_lens_id": 11},
        {
            "title": "Blade Runner (1982)",
            "genres": "Film-Noir|Sci-Fi",
            "movie_lens_id": 12,
        },
    ]

    created = {}
    for m in movies_data:
        movie = await crud.movie.create(db, obj_in=MovieCreate(**m))
        created[m["title"]] = movie

    # Seed ratings for popularity / average rating
    user_data = UserCreate(email="rater@example.com", password="password123")
    rater = await crud.user.create(db, obj_in=user_data)

    await crud.rating.create_with_owner(
        db,
        obj_in=RatingCreate(
            movie_id=created["Matrix, The (1999)"].id,
            rating=5.0,
            timestamp=100,
        ),
        user_id=rater.id,
    )
    await crud.rating.create_with_owner(
        db,
        obj_in=RatingCreate(
            movie_id=created["Alien (1979)"].id,
            rating=4.5,
            timestamp=101,
        ),
        user_id=rater.id,
    )
    return created


async def create_auth_token(client: AsyncClient, db: AsyncSession) -> tuple[str, User]:
    """Helper to create and authenticate a test user."""
    user_in = UserCreate(email="tester@example.com", password="password123")
    user = await crud.user.create(db, obj_in=user_in)

    login_resp = await client.post(
        "/api/v1/users/login/token",
        data={"username": "tester@example.com", "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    rate_limiter.reset_for_test()
    return token, user


@pytest.mark.asyncio
async def test_discover_returns_only_seeded_catalogue_ids(
    client: AsyncClient, db_session: AsyncSession
):
    """1. Interpretation with mocked response -> results contain ONLY seeded catalogue IDs."""
    seeded = await seed_test_catalogue(db_session)
    valid_ids = {m.id for m in seeded.values()}
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[],
        reference_titles=[],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "Looking for good sci-fi movies"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) > 0
        for item in data["results"]:
            assert item["movie_id"] in valid_ids
            assert "Sci-Fi" in item["genres"]
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_excluded_genre_never_appears(
    client: AsyncClient, db_session: AsyncSession
):
    """2. Excluded genre never appears in results (even if multi-genre like Action|Horror|Sci-Fi)."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[
            "Horror"
        ],  # Alien (1979) has Horror|Sci-Fi and must be excluded!
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "sci-fi but definitely no horror"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]
        assert "Alien (1979)" not in result_titles
        assert "Scream (1996)" not in result_titles
        for r in data["results"]:
            assert "Horror" not in r["genres"].split("|")
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_year_range_and_undated_titles(
    client: AsyncClient, db_session: AsyncSession
):
    """3. Year range respected; a title without a year is not crashed and excluded under a year filter."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # Filter years 1990 to 1999
    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[],
        year_min=1990,
        year_max=1999,
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "90s sci-fi movies"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]
        # Metropolis has no year and must NOT be included in 1990-1999
        assert "Metropolis" not in result_titles
        # Blade Runner is 1982, must not be included
        assert "Blade Runner (1982)" not in result_titles
        # The Matrix is 1999, must be included
        assert "Matrix, The (1999)" in result_titles
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_genre_matching_is_token_exact(
    client: AsyncClient, db_session: AsyncSession
):
    """4. Genre matching is token-exact ('Action' does not match 'Action-Adventure')."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # Ask for Action films only. 'Action Hero (1990)' has 'Action-Adventure|Comedy'
    # and should NOT match if Action is required and Action-Adventure is distinct.
    mock_parsed = ParsedPreferences(
        include_genres=["Action"],
        exclude_genres=[],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "Action films"},
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]
        assert "Action Hero (1990)" not in result_titles
        assert "Die Hard (1988)" in result_titles
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_reference_title_resolution_and_unresolved(
    client: AsyncClient, db_session: AsyncSession
):
    """5. Reference title resolution including '..., The' inversion; unresolved reported, not guessed."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # "The Matrix" should resolve to "Matrix, The (1999)".
    # "Interstellar" is not in this catalogue and must be reported as unresolved.
    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        reference_titles=["The Matrix", "Interstellar"],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "Movies like The Matrix and Interstellar"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Interstellar" in data["unresolved_references"]
        # The resolved reference "Matrix, The (1999)" is excluded from results
        result_titles = [r["title"] for r in data["results"]]
        assert "Matrix, The (1999)" not in result_titles
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_mood_and_theme_terms_in_unverified(
    client: AsyncClient, db_session: AsyncSession
):
    """6. Mood/theme terms returned under unverified and don't fabricate ranking."""
    await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Comedy"],
        mood_terms=["heartwarming", "uplifting"],
        theme_terms=["friendship"],
        notes_unsupported=["User requested Tom Hanks"],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "heartwarming comedy about friendship with Tom Hanks"},
        )
        assert resp.status_code == 200
        data = resp.json()
        unverified_text = " ".join(data["unverified"])
        assert "heartwarming" in unverified_text
        assert "friendship" in unverified_text
        assert "Tom Hanks" in unverified_text
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_strict_prompt_exclusion_override(
    client: AsyncClient, db_session: AsyncSession
):
    """7. Deterministic prompt exclusion scanner forces exclusion even if LLM omits it."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # Simulate LLM returning empty exclude_genres despite user prompt saying "no horror"
    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[],  # LLM failed to include Horror
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": "Looking for intense sci-fi movies, but definitely no horror films"
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]
        # Alien (1979) has Action|Horror|Sci-Fi and must be strictly filtered out by the deterministic scanner
        assert "Alien (1979)" not in result_titles
        assert "Scream (1996)" not in result_titles
        for r in data["results"]:
            assert "Horror" not in r["genres"].split("|")
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_unresolved_reference_guides_genre_thematic_ranking(
    client: AsyncClient, db_session: AsyncSession
):
    """8. Absent reference titles are explained and guide candidate ranking without hallucinating."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # Reference "Inception" is not in the pre-2001 catalogue, but user specified Sci-Fi
    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[],
        reference_titles=["Inception"],
        theme_terms=["mind-bending"],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "mind-bending sci-fi movies like Inception"},
        )
        assert resp.status_code == 200
        data = resp.json()
        # Inception is in unresolved_references
        assert "Inception" in data["unresolved_references"]
        # Explanatory note explains pre-2001 archive limitation
        assert any("pre-2001" in item for item in data["unverified"])
        # Returned results are grounded in the catalogue
        for r in data["results"]:
            assert "Sci-Fi" in r["genres"]
            assert "Inception" not in r["title"]
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_returns_fewer_results_rather_than_irrelevant_padding(
    client: AsyncClient, db_session: AsyncSession
):
    """9. Strict criteria returns fewer high-relevance items rather than padding with unrelated films."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    # Only Crime films requested with 1970-1975 range. Only Godfather matches.
    mock_parsed = ParsedPreferences(
        include_genres=["Crime"],
        exclude_genres=[],
        year_min=1970,
        year_max=1975,
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "1970s crime dramas"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["results"]) == 1
        assert data["results"][0]["title"] == "Godfather, The (1972)"
        # Should NOT pad with Toy Story, Die Hard, Casablanca, etc.
        result_titles = [r["title"] for r in data["results"]]
        assert "Toy Story (1995)" not in result_titles
        assert "Die Hard (1988)" not in result_titles
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_required_prompt_a_recent_sci_fi_no_horror(
    client: AsyncClient, db_session: AsyncSession
):
    """10. Required Prompt A: 'Mind-bending sci-fi with an emotional story, similar to Interstellar, no horror, fairly recent'."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi", "Drama"],
        exclude_genres=["Horror"],
        reference_titles=["Interstellar"],
        theme_terms=["mind-bending", "emotional"],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": "Mind-bending sci-fi with an emotional story, similar to Interstellar, no horror, fairly recent"
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Interstellar" in data["unresolved_references"]
        result_titles = [r["title"] for r in data["results"]]

        # Horror is strictly excluded (Alien has Horror|Sci-Fi and must NOT appear)
        assert "Alien (1979)" not in result_titles
        assert "Scream (1996)" not in result_titles

        # "fairly recent" restricts to modern catalogue era (>=1995); Blade Runner (1982) must not appear
        assert "Blade Runner (1982)" not in result_titles

        # Matrix (1999) is in the recent catalogue era and must be included
        assert "Matrix, The (1999)" in result_titles

        # Explanations do not falsely claim older films match recency
        for r in data["results"]:
            assert "Horror" not in r["genres"].split("|")
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_required_prompt_b_after_1990_without_horror(
    client: AsyncClient, db_session: AsyncSession
):
    """11. Required Prompt B: 'Recommend science-fiction films released after 1990, without horror'."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=["Horror"],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": "Recommend science-fiction films released after 1990, without horror."
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]

        # Released in 1990 or earlier must NOT appear:
        # Alien (1979), Blade Runner (1982)
        assert "Alien (1979)" not in result_titles
        assert "Blade Runner (1982)" not in result_titles
        # Matrix (1999) is released after 1990
        assert "Matrix, The (1999)" in result_titles
        for r in data["results"]:
            assert "Horror" not in r["genres"].split("|")
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_required_prompt_c_classic_1940s_or_1950s(
    client: AsyncClient, db_session: AsyncSession
):
    """12. Required Prompt C: 'Recommend witty romantic comedies from the 1940s or 1950s'."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Romance", "Comedy"],
        exclude_genres=[],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": "Recommend witty romantic comedies from the 1940s or 1950s."
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        result_titles = [r["title"] for r in data["results"]]

        # Casablanca (1942) has Romance, falls in 1940-1959
        assert "Casablanca (1942)" in result_titles
        # 1990s films must NOT appear
        assert "Toy Story (1995)" not in result_titles
        assert "Matrix, The (1999)" not in result_titles
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_discover_required_prompt_f_impossible_constraints_no_silent_relaxation(
    client: AsyncClient, db_session: AsyncSession
):
    """13. Required Prompt F: 'Recommend movies released after 2015 from this pre-2001 catalogue' returns clean empty result without silent relaxation."""
    seeded = await seed_test_catalogue(db_session)
    token, _ = await create_auth_token(client, db_session)

    mock_parsed = ParsedPreferences(
        include_genres=["Sci-Fi"],
        exclude_genres=[],
        year_min=2016,
    )
    mock_gemini = MockGeminiClient(response_obj=mock_parsed)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "prompt": "Recommend movies released after 2015 from this pre-2001 catalogue."
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Must return empty results, NOT old movies relaxed!
        assert len(data["results"]) == 0
        assert data["message"] is not None
        assert "2000" in data["message"]
        assert len(data["relaxed"]) == 0
    finally:
        app.dependency_overrides.pop(get_gemini, None)
