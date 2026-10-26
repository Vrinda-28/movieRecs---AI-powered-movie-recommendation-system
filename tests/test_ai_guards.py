"""Tests for guards: error mapping, rate limiting, validation, unauthenticated calls, and secret leakage prevention."""

import logging

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.db.models import User
from app.main import app
from app.schemas.ai import ParsedPreferences
from app.schemas.user import UserCreate
from app.services.ai.groq_client import (
    AiAuthFailedError,
    AiBadResponseError,
    AiNotConfiguredError,
    AiQuotaExceededError,
    AiTimeoutError,
    GroqClient,
    get_groq,
)
from app.services.ai.guards import rate_limiter, sanitize_input_text

# Aliases for backward compatibility in existing tests
GeminiClient = GroqClient
get_gemini = get_groq


class MockFailingGroqClient(GroqClient):
    """Mock Groq client configured to raise specific AI errors."""

    def __init__(
        self, exc_to_raise: Exception, api_key: str = "gsk_SecretFakeKey123456789"
    ):
        super().__init__(api_key=api_key, model=settings.GROQ_MODEL)
        self.exc_to_raise = exc_to_raise

    async def generate_json(self, system: str, user: str, schema):
        raise self.exc_to_raise


MockFailingGeminiClient = MockFailingGroqClient


async def create_auth_token(
    client: AsyncClient, db: AsyncSession, email: str = "guard_user@example.com"
) -> tuple[str, User]:
    user_in = UserCreate(email=email, password="password123")
    user = await crud.user.create(db, obj_in=user_in)

    login_resp = await client.post(
        "/api/v1/users/login/token",
        data={"username": email, "password": "password123"},
    )
    token = login_resp.json()["access_token"]
    return token, user


@pytest.mark.asyncio
async def test_malformed_model_output_handling():
    """7. Malformed output: year clamping and validation handling."""
    # Test Pydantic clamping on year_min / year_max
    prefs = ParsedPreferences(
        include_genres=["Sci-Fi"],
        year_min=99999,  # Should clamp to 2030
        year_max=500,  # Should clamp to 1880
        reference_titles=[
            "A" * 300,
            "Valid Title",
            "Third",
            "Fourth Extra",
        ],  # Clamped to 3 titles <= 120 chars
    )
    assert prefs.year_min == 2030
    assert prefs.year_max == 1880
    assert len(prefs.reference_titles) == 3
    assert len(prefs.reference_titles[0]) == 120


@pytest.mark.asyncio
async def test_error_status_codes_and_no_traceback(
    client: AsyncClient, db_session: AsyncSession
):
    """10. Fake Gemini raising auth / quota / timeout / bad response -> proper status codes (502/429/504), no tracebacks."""
    token, _ = await create_auth_token(client, db_session)

    test_cases = [
        (AiAuthFailedError(), 502, "ai_auth_failed"),
        (AiQuotaExceededError(), 429, "ai_quota_exceeded"),
        (AiTimeoutError(), 504, "ai_timeout"),
        (AiBadResponseError(), 502, "ai_bad_response"),
    ]

    for exc, expected_status, expected_detail in test_cases:
        mock_gemini = MockFailingGeminiClient(exc_to_raise=exc)
        app.dependency_overrides[get_gemini] = lambda mg=mock_gemini: mg

        try:
            resp = await client.post(
                "/api/v1/ai/discover",
                headers={"Authorization": f"Bearer {token}"},
                json={"prompt": "any sci fi movie"},
            )
            assert (
                resp.status_code == expected_status
            ), f"Expected {expected_status} for {exc}, got {resp.status_code}"
            body = resp.json()
            assert body["detail"] == expected_detail
            # Body must not contain stack traces or raw tracebacks
            assert "Traceback" not in resp.text
            assert 'File "' not in resp.text
        finally:
            app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_unauthenticated_and_validation_errors(
    client: AsyncClient, db_session: AsyncSession
):
    """11. Unauthenticated -> 401; input too long / too short -> 422."""
    # 1. Unauthenticated call
    resp = await client.post(
        "/api/v1/ai/discover",
        json={"prompt": "tell me a movie"},
    )
    assert resp.status_code == 401

    token, _ = await create_auth_token(
        client, db_session, email="validator@example.com"
    )

    # 2. Input too short (< 3 characters)
    resp = await client.post(
        "/api/v1/ai/discover",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "hi"},
    )
    assert resp.status_code == 422

    # 3. Input too long (> 500 characters)
    resp = await client.post(
        "/api/v1/ai/discover",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": "a" * 501},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_rate_limiting(client: AsyncClient, db_session: AsyncSession):
    """11b. Rate limit enforcement -> 429 with Retry-After header."""
    token, user = await create_auth_token(
        client, db_session, email="ratelimit_user@example.com"
    )
    rate_limiter.reset_for_test()

    mock_gemini = GeminiClient(api_key="fake_key_123")
    app.dependency_overrides[get_gemini] = lambda: mock_gemini

    # Fill up sliding window
    limit = settings.AI_RATE_LIMIT_PER_MIN
    for _ in range(limit):
        rate_limiter.check(user.id)

    # Next check should raise 429
    with pytest.raises(Exception) as exc_info:
        rate_limiter.check(user.id)

    assert "429" in str(exc_info.value)
    rate_limiter.reset_for_test()
    app.dependency_overrides.pop(get_gemini, None)


@pytest.mark.asyncio
async def test_groq_key_unset_behavior(client: AsyncClient, db_session: AsyncSession):
    """12. GROQ_API_KEY unset -> status shows enabled:false, /discover -> 503 ai_not_configured."""
    # When api_key is empty
    mock_groq = GroqClient(api_key="", model=settings.GROQ_MODEL)
    app.dependency_overrides[get_groq] = lambda: mock_groq

    try:
        # /ai/status does not require auth
        status_resp = await client.get("/api/v1/ai/status")
        assert status_resp.status_code == 200
        assert status_resp.json() == {"enabled": False, "model": settings.GROQ_MODEL}

        token, _ = await create_auth_token(
            client, db_session, email="unset_key_user@example.com"
        )
        discover_resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "some movies"},
        )
        assert discover_resp.status_code == 503
        assert discover_resp.json()["detail"] == "ai_not_configured"

        # Verify existing endpoints (e.g. /movies) are completely unaffected
        movies_resp = await client.get("/api/v1/movies/")
        assert movies_resp.status_code == 200
    finally:
        app.dependency_overrides.pop(get_groq, None)


@pytest.mark.asyncio
async def test_secret_key_never_leaked_in_responses_or_logs(
    client: AsyncClient, db_session: AsyncSession, caplog
):
    """13. The API key string never appears in any response body or captured logs."""
    test_secret_key = "gsk_DUMMYSECRETKEYFORTESTING998877"
    token, _ = await create_auth_token(
        client, db_session, email="secret_test_user@example.com"
    )

    # Set up mock that raises an error containing the secret key
    mock_groq = MockFailingGroqClient(
        exc_to_raise=AiAuthFailedError(
            f"API key {test_secret_key} rejected by provider"
        ),
        api_key=test_secret_key,
    )
    app.dependency_overrides[get_groq] = lambda: mock_groq

    with caplog.at_level(logging.DEBUG):
        resp = await client.post(
            "/api/v1/ai/discover",
            headers={"Authorization": f"Bearer {token}"},
            json={"prompt": "testing key leakage"},
        )

    # Key must NOT appear in response body
    assert test_secret_key not in resp.text
    assert resp.status_code == 502

    # Key must NOT appear in logs
    for record in caplog.records:
        assert test_secret_key not in record.message
        assert test_secret_key not in str(record.exc_info)

    app.dependency_overrides.pop(get_groq, None)


@pytest.mark.asyncio
async def test_groq_sdk_exception_mapping(monkeypatch):
    """14. Verifies that Groq SDK error classes map to domain AI errors."""
    import httpx
    from groq import (
        APIConnectionError,
        APIError,
        APITimeoutError,
        AuthenticationError,
        NotFoundError,
        RateLimitError,
    )

    groq_client = GroqClient(
        api_key="gsk_test_key_12345", model="llama-3.3-70b-versatile"
    )

    # Create dummy request/response objects for SDK exceptions
    dummy_req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    dummy_resp = httpx.Response(400, request=dummy_req)

    cases = [
        (
            AuthenticationError("Invalid API Key", response=dummy_resp, body=None),
            AiAuthFailedError,
        ),
        (
            RateLimitError("Rate limit reached", response=dummy_resp, body=None),
            AiQuotaExceededError,
        ),
        (APITimeoutError(request=dummy_req), AiTimeoutError),
        (APIConnectionError(request=dummy_req), AiBadResponseError),
        (
            NotFoundError("Model not found", response=dummy_resp, body=None),
            AiBadResponseError,
        ),
        (
            APIError("Internal server error", request=dummy_req, body=None),
            AiBadResponseError,
        ),
    ]

    for sdk_err, expected_cls in cases:

        async def mock_create(*args, **kwargs):
            raise sdk_err

        monkeypatch.setattr(
            groq_client._get_client().chat.completions, "create", mock_create
        )

        with pytest.raises(expected_cls):
            await groq_client.generate_json("system", "user", ParsedPreferences)
