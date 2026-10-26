"""Tests for grounded Q&A service ('Ask About Movies')."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.db.models import User
from app.main import app
from app.schemas.ai import AskAnswer
from app.schemas.movie import MovieCreate
from app.schemas.rating import RatingCreate
from app.schemas.user import UserCreate
from app.services.ai.groq_client import GroqClient, get_groq

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
    """Seeds a test catalogue with movies."""
    movies_data = [
        {
            "title": "Matrix, The (1999)",
            "genres": "Action|Sci-Fi",
            "movie_lens_id": 201,
        },
        {
            "title": "Blade Runner (1982)",
            "genres": "Film-Noir|Sci-Fi",
            "movie_lens_id": 202,
        },
        {
            "title": "Alien (1979)",
            "genres": "Action|Horror|Sci-Fi",
            "movie_lens_id": 203,
        },
        {
            "title": "Toy Story (1995)",
            "genres": "Animation|Children's|Comedy",
            "movie_lens_id": 204,
        },
    ]

    created = {}
    for m in movies_data:
        movie = await crud.movie.create(db, obj_in=MovieCreate(**m))
        created[m["title"]] = movie

    return created


async def create_auth_token(client: AsyncClient, db: AsyncSession) -> tuple[str, User]:
    user_in = UserCreate(email="asker@example.com", password="password123")
    user = await crud.user.create(db, obj_in=user_in)

    login_resp = await client.post(
        "/api/v1/users/login/token",
        data={"username": "asker@example.com", "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    return token, user


@pytest.mark.asyncio
async def test_ask_hallucinated_movie_ids_dropped(
    client: AsyncClient, db_session: AsyncSession
):
    """8. Hallucinated movie_ids in an Ask answer are dropped; only candidate-set IDs survive."""
    seeded = await seed_test_catalogue(db_session)
    matrix = seeded["Matrix, The (1999)"]
    token, _ = await create_auth_token(client, db_session)

    # Return valid candidate ID + hallucinated IDs (9999, 8888)
    blade_runner = seeded["Blade Runner (1982)"]
    mock_answer = AskAnswer(
        answer="I recommend Blade Runner as a similar sci-fi classic.",
        catalogue_facts=[
            "The Matrix was released in 1999 with genres Action and Sci-Fi."
        ],
        interpretation=["Both films explore dystopian themes."],
        cannot_verify=[
            "Cast, director, and plot details cannot be verified from catalogue data."
        ],
        movie_ids=[blade_runner.id, 9999, 8888],  # 9999 and 8888 are hallucinated!
    )
    mock_gemini = MockGeminiClient(response_obj=mock_answer)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "What movies are similar to The Matrix?",
                "movie_id": matrix.id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert blade_runner.id in data["movie_ids"]
        assert 9999 not in data["movie_ids"]
        assert 8888 not in data["movie_ids"]
        # Confirm hydrated cards only contain Blade Runner
        returned_card_ids = [m["movie_id"] for m in data["movies"]]
        assert returned_card_ids == [blade_runner.id]
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_ask_plot_unverified_strict_mode(
    client: AsyncClient, db_session: AsyncSession
):
    """9. Ask for movie with no plot -> response contains cannot_verify entry and no invented plot."""
    seeded = await seed_test_catalogue(db_session)
    matrix = seeded["Matrix, The (1999)"]
    token, _ = await create_auth_token(client, db_session)

    mock_answer = AskAnswer(
        answer="Our catalogue does not store plot synopses, characters, or cast. It only records title, year, genres, and ratings.",
        catalogue_facts=["Title: The Matrix (1999)", "Genres: Action|Sci-Fi"],
        interpretation=[],
        cannot_verify=[
            "Plot synopsis, cast, runtime, and age ratings cannot be verified from catalogue data."
        ],
        movie_ids=[],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_answer)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "What is this movie about?",
                "movie_id": matrix.id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["cannot_verify"]) > 0
        cannot_verify_str = " ".join(data["cannot_verify"]).lower()
        assert "plot" in cannot_verify_str or "synopsis" in cannot_verify_str
    finally:
        app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_ask_recommendation_fallback_to_candidate_cards(
    client: AsyncClient, db_session: AsyncSession
):
    """Ask for recommendations returns real candidate cards even if model returned 0 movie_ids."""
    seeded = await seed_test_catalogue(db_session)
    matrix = seeded["Matrix, The (1999)"]
    token, _ = await create_auth_token(client, db_session)

    # Model returned 0 movie_ids despite a recommendation question
    mock_answer = AskAnswer(
        answer="Here are some similar sci-fi films from our catalogue.",
        catalogue_facts=["The Matrix is an Action and Sci-Fi title."],
        interpretation=[],
        cannot_verify=[],
        movie_ids=[],
    )
    mock_gemini = MockGeminiClient(response_obj=mock_answer)
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    try:
        resp = await client.post(
            "/api/v1/ai/ask",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "question": "Recommend similar movies from our catalogue",
                "movie_id": matrix.id,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # Fallback populated candidate IDs
        assert len(data["movie_ids"]) > 0
        assert len(data["movies"]) > 0
        for m in data["movies"]:
            assert m["movie_id"] != matrix.id  # Does not recommend itself
    finally:
        app.dependency_overrides.pop(get_gemini, None)
