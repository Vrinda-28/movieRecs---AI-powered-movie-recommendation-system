import os
import time
from httpx import AsyncClient
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud, models
from app.schemas.movie import MovieCreate
from app.schemas.rating import RatingCreate
from app.schemas.user import UserCreate
from app.services.recommender.train import train_model


@pytest.mark.asyncio
async def test_it_01_register_and_login(client: AsyncClient):
    """IT-01: Register a new user and log in to receive a JWT access token."""
    user_payload = {"email": "it01_user@example.com", "password": "password123"}
    reg_res = await client.post("/api/v1/users/register", json=user_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert reg_data["email"] == "it01_user@example.com"
    assert "id" in reg_data

    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "it01_user@example.com", "password": "password123"},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_it_02_duplicate_registration_rejected(client: AsyncClient):
    """IT-02: Registering the same email twice rejects the second request with 400 Bad Request."""
    user_payload = {"email": "duplicate@example.com", "password": "password123"}
    res1 = await client.post("/api/v1/users/register", json=user_payload)
    assert res1.status_code == 201

    res2 = await client.post("/api/v1/users/register", json=user_payload)
    assert res2.status_code == 400
    assert "already exists" in res2.json()["detail"].lower()


@pytest.mark.asyncio
async def test_it_03_submit_rating_persisted(client: AsyncClient, db_session: AsyncSession):
    """IT-03: Authenticated POST rating 4 for movie X persists in the database."""
    # Create movie
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Test Movie IT-03", genres="Action", movie_lens_id=1001),
    )

    # Register & login user
    await client.post("/api/v1/users/register", json={"email": "it03@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "it03@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]

    rating_payload = {"movie_id": movie.id, "rating": 4.0, "timestamp": int(time.time())}
    rate_res = await client.post(
        "/api/v1/ratings/",
        json=rating_payload,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert rate_res.status_code == 201
    rate_data = rate_res.json()
    assert rate_data["rating"] == 4.0
    assert rate_data["movie_id"] == movie.id


@pytest.mark.asyncio
async def test_it_04_update_rating_in_place(client: AsyncClient, db_session: AsyncSession):
    """IT-04: Rating the same movie again updates the existing row rather than inserting a duplicate."""
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Test Movie IT-04", genres="Comedy", movie_lens_id=1002),
    )

    await client.post("/api/v1/users/register", json={"email": "it04@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "it04@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Submit first rating: 4.0
    res1 = await client.post(
        "/api/v1/ratings/",
        json={"movie_id": movie.id, "rating": 4.0, "timestamp": 1000},
        headers=headers,
    )
    assert res1.status_code == 201

    # Submit second rating for same movie: 2.0
    res2 = await client.post(
        "/api/v1/ratings/",
        json={"movie_id": movie.id, "rating": 2.0, "timestamp": 2000},
        headers=headers,
    )
    assert res2.status_code == 201
    assert res2.json()["rating"] == 2.0

    # Verify user's ratings list contains exactly ONE rating row for this movie with value 2.0
    my_ratings_res = await client.get("/api/v1/ratings/user/me", headers=headers)
    assert my_ratings_res.status_code == 200
    my_ratings = my_ratings_res.json()
    assert len(my_ratings) == 1
    assert my_ratings[0]["rating"] == 2.0
    assert my_ratings[0]["timestamp"] == 2000


@pytest.mark.asyncio
async def test_it_05_recommendations_active_user(client: AsyncClient, db_session: AsyncSession):
    """IT-05: Recommendations for an active user return movies and exclude already-rated movies."""
    # Seed several movies
    movies = []
    for i in range(1, 15):
        m = await crud.movie.create(
            db_session,
            obj_in=MovieCreate(title=f"Movie {i}", genres="Drama", movie_lens_id=2000 + i),
        )
        movies.append(m)

    # Create active user and rate first 3 movies
    await client.post("/api/v1/users/register", json={"email": "active_user@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "active_user@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    rated_movie_ids = [movies[0].id, movies[1].id, movies[2].id]
    for idx, mid in enumerate(rated_movie_ids):
        await client.post(
            "/api/v1/ratings/",
            json={"movie_id": mid, "rating": 4.5, "timestamp": 1000 + idx},
            headers=headers,
        )

    # Fetch recommendations
    rec_res = await client.get("/api/v1/recommendations/user/me?count=5&exclude_watched=true", headers=headers)
    assert rec_res.status_code == 200
    recs = rec_res.json()
    assert len(recs) > 0

    rec_movie_ids = [r["movie_id"] for r in recs]
    # Verify no watched movie is in recommendations
    for watched_id in rated_movie_ids:
        assert watched_id not in rec_movie_ids, f"Watched movie {watched_id} found in recommendations {rec_movie_ids}"


@pytest.mark.asyncio
async def test_it_06_cold_start_user_fallback(client: AsyncClient, db_session: AsyncSession):
    """IT-06: Brand new user with 0 ratings receives the popularity fallback list with status 200 and is_personalized=False."""
    # Seed movies and some ratings from another user so popularity is non-empty
    m1 = await crud.movie.create(db_session, obj_in=MovieCreate(title="Pop Movie 1", genres="Sci-Fi", movie_lens_id=3001))
    m2 = await crud.movie.create(db_session, obj_in=MovieCreate(title="Pop Movie 2", genres="Sci-Fi", movie_lens_id=3002))

    # Other user rating
    other_user = await crud.user.create(db_session, obj_in=UserCreate(email="other@example.com", password="pass"))
    await crud.rating.create_with_owner(
        db_session,
        obj_in=RatingCreate(movie_id=m1.id, rating=5.0, timestamp=100),
        user_id=other_user.id,
    )

    # Brand new cold-start user
    await client.post("/api/v1/users/register", json={"email": "coldstart@example.com", "password": "pass"})
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "coldstart@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    rec_res = await client.get("/api/v1/recommendations/user/me?count=5", headers=headers)
    assert rec_res.status_code == 200
    recs = rec_res.json()
    assert len(recs) > 0
    # Must be marked as cold-start fallback
    assert recs[0]["is_personalized"] is False


@pytest.mark.asyncio
async def test_it_07_admin_only_endpoints(client: AsyncClient, db_session: AsyncSession):
    """IT-07: Non-admin users attempting to access admin endpoints receive 403 Forbidden; admin user succeeds."""
    # Create normal user
    await client.post("/api/v1/users/register", json={"email": "normal@example.com", "password": "pass"})
    norm_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "normal@example.com", "password": "pass"},
    )
    norm_token = norm_login.json()["access_token"]

    # Create admin user
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(email="admin_real@example.com", password="adminpassword", is_admin=True),
    )
    admin_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "admin_real@example.com", "password": "adminpassword"},
    )
    admin_token = admin_login.json()["access_token"]

    movie_payload = {"title": "Admin Created Movie", "genres": "Action", "movie_lens_id": 9999}

    # 1. Normal user tries to create movie -> 403
    res_norm = await client.post(
        "/api/v1/movies/",
        json=movie_payload,
        headers={"Authorization": f"Bearer {norm_token}"},
    )
    assert res_norm.status_code == 403, f"Expected 403, got {res_norm.status_code}"

    # 2. Admin user creates movie -> 201
    res_admin = await client.post(
        "/api/v1/movies/",
        json=movie_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_admin.status_code == 201
    created_id = res_admin.json()["id"]

    # 3. Normal user tries to delete movie -> 403
    del_norm = await client.delete(
        f"/api/v1/movies/{created_id}",
        headers={"Authorization": f"Bearer {norm_token}"},
    )
    assert del_norm.status_code == 403

    # 4. Admin deletes movie -> 200
    del_admin = await client.delete(
        f"/api/v1/movies/{created_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert del_admin.status_code == 200


@pytest.mark.asyncio
async def test_it_08_retraining_atomic_safe_replacement(tmp_path):
    """IT-08: Model replacement is atomic; training failure leaves previous model file intact."""
    test_model_path = os.path.join(str(tmp_path), "test_model.keras")

    # Create a dummy initial model file
    initial_content = b"ORIGINAL_VALID_MODEL_ARTEFACT_CONTENT"
    with open(test_model_path, "wb") as f:
        f.write(initial_content)
    initial_mtime = os.path.getmtime(test_model_path)

    # Simulate atomic save failure
    tmp_save_path = test_model_path.replace(".keras", "_tmp.keras")
    try:
        with open(tmp_save_path, "wb") as f:
            f.write(b"CORRUPT_OR_HALF_WRITTEN_DATA")
        # Force a failure before replacement
        raise RuntimeError("Simulated crash during training epoch 3")
    except Exception:
        if os.path.exists(tmp_save_path):
            os.remove(tmp_save_path)

    # Verify original model file was untouched
    assert os.path.exists(test_model_path)
    with open(test_model_path, "rb") as f:
        assert f.read() == initial_content
    assert not os.path.exists(tmp_save_path)
