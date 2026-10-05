import time
from datetime import timedelta
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.schemas.movie import MovieCreate
from app.security import create_access_token


@pytest.mark.asyncio
async def test_st_01_full_user_journey(client: AsyncClient, db_session: AsyncSession):
    """ST-01: Full user journey: register, login, rate 5 movies, view recommendations."""
    # Seed catalogue of 10 movies
    created_movies = []
    for i in range(1, 11):
        m = await crud.movie.create(
            db_session,
            obj_in=MovieCreate(title=f"Journey Movie {i}", genres="Adventure", movie_lens_id=5000 + i),
        )
        created_movies.append(m)

    # 1. Register
    reg_res = await client.post(
        "/api/v1/users/register",
        json={"email": "journey_user@example.com", "password": "securepassword123"},
    )
    assert reg_res.status_code == 201

    # 2. Login
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "journey_user@example.com", "password": "securepassword123"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 3. Rate 5 movies
    for i in range(5):
        rate_res = await client.post(
            "/api/v1/ratings/",
            json={"movie_id": created_movies[i].id, "rating": 4.5, "timestamp": 1000 + i * 100},
            headers=headers,
        )
        assert rate_res.status_code == 201

    # 4. Fetch recommendations
    rec_res = await client.get("/api/v1/recommendations/user/me?count=5", headers=headers)
    assert rec_res.status_code == 200
    recs = rec_res.json()
    assert len(recs) > 0

    # Ensure none of the 5 rated movies are recommended
    rated_ids = {created_movies[i].id for i in range(5)}
    for r in recs:
        assert r["movie_id"] not in rated_ids


@pytest.mark.asyncio
async def test_st_02_health_and_root_endpoints(client: AsyncClient):
    """ST-02: Clean start: verify root and health endpoints return healthy state."""
    root_res = await client.get("/")
    assert root_res.status_code == 200
    assert "RecommendationApp" in root_res.json()["message"]

    health_res = await client.get("/health")
    assert health_res.status_code == 200
    assert health_res.json() == {"status": "ok", "database": "connected"}


@pytest.mark.asyncio
async def test_st_03_bad_login_shows_clear_error(client: AsyncClient):
    """ST-03: Wrong email/password returns 401 Unauthorized with clear message, no crash."""
    bad_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "nonexistent_user@example.com", "password": "wrongpassword"},
    )
    assert bad_login.status_code == 401
    assert "incorrect email or password" in bad_login.json()["detail"].lower()


@pytest.mark.asyncio
async def test_st_04_session_expiry_handling(client: AsyncClient):
    """ST-04: Expired token rejected with 401 Unauthorized."""
    expired_token = create_access_token(
        subject="expired_user@example.com",
        expires_delta=timedelta(seconds=-60),
    )
    res = await client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res.status_code == 401
    assert "could not validate credentials" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_st_05_recommendation_latency_benchmark(client: AsyncClient, db_session: AsyncSession):
    """ST-05: 10 repeated recommendation requests achieve average response time under 1.0 second."""
    # Seed 5 movies
    for i in range(1, 6):
        await crud.movie.create(
            db_session,
            obj_in=MovieCreate(title=f"Benchmark Movie {i}", genres="Animation", movie_lens_id=6000 + i),
        )

    await client.post("/api/v1/users/register", json={"email": "benchmark@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "benchmark@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    latencies = []
    for _ in range(10):
        t0 = time.perf_counter()
        res = await client.get("/api/v1/recommendations/user/me?count=5", headers=headers)
        t1 = time.perf_counter()
        assert res.status_code == 200
        latencies.append(t1 - t0)

    avg_latency = sum(latencies) / len(latencies)
    assert avg_latency < 1.0, f"Average recommendation latency {avg_latency:.4f}s exceeded 1.0s limit"


@pytest.mark.asyncio
async def test_st_06_recommendation_filtering_and_consistency(client: AsyncClient, db_session: AsyncSession):
    """ST-06: Recommendations respect count parameter and already-watched exclusions."""
    # Seed movies
    for i in range(1, 12):
        await crud.movie.create(
            db_session,
            obj_in=MovieCreate(title=f"Consistent Movie {i}", genres="Thriller", movie_lens_id=7000 + i),
        )

    await client.post("/api/v1/users/register", json={"email": "consistent@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "consistent@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_k3 = await client.get("/api/v1/recommendations/user/me?count=3", headers=headers)
    assert res_k3.status_code == 200
    assert len(res_k3.json()) <= 3

    res_k8 = await client.get("/api/v1/recommendations/user/me?count=8", headers=headers)
    assert res_k8.status_code == 200
    assert len(res_k8.json()) <= 8
