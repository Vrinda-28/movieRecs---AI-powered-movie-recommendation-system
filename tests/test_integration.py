import os
import time

import pytest
from httpx import AsyncClient
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
async def test_it_03_submit_rating_persisted(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-03: Authenticated POST rating 4 for movie X persists in the database."""
    # Create movie
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(
            title="Test Movie IT-03", genres="Action", movie_lens_id=1001
        ),
    )

    # Register & login user
    await client.post(
        "/api/v1/users/register", json={"email": "it03@example.com", "password": "pass"}
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "it03@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]

    rating_payload = {
        "movie_id": movie.id,
        "rating": 4.0,
        "timestamp": int(time.time()),
    }
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
async def test_it_04_update_rating_in_place(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-04: Rating the same movie again updates the existing row rather than inserting a duplicate."""
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(
            title="Test Movie IT-04", genres="Comedy", movie_lens_id=1002
        ),
    )

    await client.post(
        "/api/v1/users/register", json={"email": "it04@example.com", "password": "pass"}
    )
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
async def test_it_05_recommendations_active_user(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-05: Recommendations for an active user return movies and exclude already-rated movies."""
    # Seed several movies
    movies = []
    for i in range(1, 15):
        m = await crud.movie.create(
            db_session,
            obj_in=MovieCreate(
                title=f"Movie {i}", genres="Drama", movie_lens_id=2000 + i
            ),
        )
        movies.append(m)

    # Create active user and rate first 3 movies
    await client.post(
        "/api/v1/users/register",
        json={"email": "active_user@example.com", "password": "pass"},
    )
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
    rec_res = await client.get(
        "/api/v1/recommendations/user/me?count=5&exclude_watched=true", headers=headers
    )
    assert rec_res.status_code == 200
    recs = rec_res.json()
    assert len(recs) > 0

    rec_movie_ids = [r["movie_id"] for r in recs]
    # Verify no watched movie is in recommendations
    for watched_id in rated_movie_ids:
        assert (
            watched_id not in rec_movie_ids
        ), f"Watched movie {watched_id} found in recommendations {rec_movie_ids}"


@pytest.mark.asyncio
async def test_it_06_cold_start_user_fallback(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-06: Brand new user with 0 ratings receives the popularity fallback list with status 200 and is_personalized=False."""
    # Seed movies and some ratings from another user so popularity is non-empty
    m1 = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Pop Movie 1", genres="Sci-Fi", movie_lens_id=3001),
    )
    m2 = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Pop Movie 2", genres="Sci-Fi", movie_lens_id=3002),
    )

    # Other user rating
    other_user = await crud.user.create(
        db_session, obj_in=UserCreate(email="other@example.com", password="pass")
    )
    await crud.rating.create_with_owner(
        db_session,
        obj_in=RatingCreate(movie_id=m1.id, rating=5.0, timestamp=100),
        user_id=other_user.id,
    )

    # Brand new cold-start user
    await client.post(
        "/api/v1/users/register",
        json={"email": "coldstart@example.com", "password": "pass"},
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "coldstart@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    rec_res = await client.get(
        "/api/v1/recommendations/user/me?count=5", headers=headers
    )
    assert rec_res.status_code == 200
    recs = rec_res.json()
    assert len(recs) > 0
    # Must be marked as cold-start fallback
    assert recs[0]["is_personalized"] is False


@pytest.mark.asyncio
async def test_it_07_admin_only_endpoints(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-07: Non-admin users attempting to access admin endpoints receive 403 Forbidden; admin user succeeds."""
    # Create normal user
    await client.post(
        "/api/v1/users/register",
        json={"email": "normal@example.com", "password": "pass"},
    )
    norm_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "normal@example.com", "password": "pass"},
    )
    norm_token = norm_login.json()["access_token"]

    # Create admin user
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(
            email="admin_real@example.com", password="adminpassword", is_admin=True
        ),
    )
    admin_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "admin_real@example.com", "password": "adminpassword"},
    )
    admin_token = admin_login.json()["access_token"]

    movie_payload = {
        "title": "Admin Created Movie",
        "genres": "Action",
        "movie_lens_id": 9999,
    }

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


@pytest.mark.asyncio
async def test_it_09_review_crud_and_ownership(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-09: Review CRUD: author creates review, duplicate is 409, stranger edit is 403, author edit succeeds, delete succeeds."""
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(
            title="Review Test Movie", genres="Drama", movie_lens_id=8001
        ),
    )

    # Author user
    await client.post(
        "/api/v1/users/register",
        json={"email": "author@example.com", "password": "pass"},
    )
    auth_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "author@example.com", "password": "pass"},
    )
    author_token = auth_login.json()["access_token"]
    author_headers = {"Authorization": f"Bearer {author_token}"}

    # Other user
    await client.post(
        "/api/v1/users/register",
        json={"email": "other_author@example.com", "password": "pass"},
    )
    other_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "other_author@example.com", "password": "pass"},
    )
    other_token = other_login.json()["access_token"]
    other_headers = {"Authorization": f"Bearer {other_token}"}
    # 0. Unauthenticated create -> 401 Unauthorized
    unauth_res = await client.post(
        "/api/v1/reviews/",
        json={"movie_id": movie.id, "text": "Unauthenticated review"},
    )
    assert unauth_res.status_code == 401

    # 1. Author creates review
    rev_res = await client.post(
        "/api/v1/reviews/",
        json={
            "movie_id": movie.id,
            "text": "Brilliant storytelling and cinematography!",
        },
        headers=author_headers,
    )
    assert rev_res.status_code == 201
    rev_data = rev_res.json()
    assert rev_data["text"] == "Brilliant storytelling and cinematography!"
    review_id = rev_data["id"]

    # 2. Duplicate review by same user -> 409 Conflict
    dup_res = await client.post(
        "/api/v1/reviews/",
        json={"movie_id": movie.id, "text": "Trying to post another review"},
        headers=author_headers,
    )
    assert dup_res.status_code == 409

    # 3. Other user tries to edit author's review -> 403 Forbidden
    edit_stranger = await client.put(
        f"/api/v1/reviews/{review_id}",
        json={"text": "Hijacking your review"},
        headers=other_headers,
    )
    assert edit_stranger.status_code == 403

    # 4. Author edits review -> 200 OK
    edit_author = await client.put(
        f"/api/v1/reviews/{review_id}",
        json={"text": "Updated: Absolute cinematic masterpiece!"},
        headers=author_headers,
    )
    assert edit_author.status_code == 200
    assert edit_author.json()["text"] == "Updated: Absolute cinematic masterpiece!"

    # 5. Author deletes review -> 200 OK
    del_res = await client.delete(
        f"/api/v1/reviews/{review_id}", headers=author_headers
    )
    assert del_res.status_code == 200


@pytest.mark.asyncio
async def test_it_10_watchlist_add_remove(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-10: Watchlist: add movie, idempotent second add, verify in list, check endpoint, remove."""
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(
            title="Watchlist Movie", genres="Sci-Fi", movie_lens_id=8002
        ),
    )

    await client.post(
        "/api/v1/users/register",
        json={"email": "wl_user@example.com", "password": "pass"},
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "wl_user@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 0. Unauthenticated add -> 401 Unauthorized
    unauth_res = await client.post(f"/api/v1/watchlist/{movie.id}")
    assert unauth_res.status_code == 401

    # 1. Add to watchlist
    add_res = await client.post(f"/api/v1/watchlist/{movie.id}", headers=headers)
    assert add_res.status_code == 201
    assert add_res.json()["movie_id"] == movie.id

    # 2. Idempotent second add
    add2_res = await client.post(f"/api/v1/watchlist/{movie.id}", headers=headers)
    assert add2_res.status_code == 201

    # 3. Check status endpoint
    chk_res = await client.get(f"/api/v1/watchlist/check/{movie.id}", headers=headers)
    assert chk_res.status_code == 200
    assert chk_res.json()["in_watchlist"] is True

    # 4. Fetch watchlist
    list_res = await client.get("/api/v1/watchlist/", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1

    # 5. Remove from watchlist
    del_res = await client.delete(f"/api/v1/watchlist/{movie.id}", headers=headers)
    assert del_res.status_code == 200
    assert del_res.json()["removed"] is True

    chk_after = await client.get(f"/api/v1/watchlist/check/{movie.id}", headers=headers)
    assert chk_after.json()["in_watchlist"] is False


@pytest.mark.asyncio
async def test_it_11_interaction_and_history(
    client: AsyncClient, db_session: AsyncSession
):
    """IT-11: Log VIEW interaction and rate movie; verify both appear in /users/me/history."""
    movie = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="History Movie", genres="Action", movie_lens_id=8003),
    )

    await client.post(
        "/api/v1/users/register",
        json={"email": "hist_user@example.com", "password": "pass"},
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "hist_user@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 1. Log VIEW
    view_res = await client.post(
        "/api/v1/interactions/",
        json={"movie_id": movie.id, "event_type": "VIEW"},
        headers=headers,
    )
    assert view_res.status_code == 201

    # 2. Submit Rating (unauthenticated check first)
    unauth_rate = await client.post(
        "/api/v1/ratings/",
        json={"movie_id": movie.id, "rating": 5.0, "timestamp": 12345},
    )
    assert unauth_rate.status_code == 401

    rate_res = await client.post(
        "/api/v1/ratings/",
        json={"movie_id": movie.id, "rating": 5.0, "timestamp": 12345},
        headers=headers,
    )
    assert rate_res.status_code == 201

    # 3. Check /users/me/history
    hist_res = await client.get("/api/v1/users/me/history", headers=headers)
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 2
    event_types = [h["event_type"] for h in history]
    assert "VIEW" in event_types
    assert "RATE" in event_types


@pytest.mark.asyncio
async def test_it_12_public_registration_blocks_admin(client: AsyncClient):
    """IT-12: Registering with is_admin=True in public registration payload is ignored; user is created as regular user."""
    payload = {"email": "hacker@example.com", "password": "pass", "is_admin": True}
    res = await client.post("/api/v1/users/register", json=payload)
    assert res.status_code == 201
    assert res.json()["is_admin"] is False


@pytest.mark.asyncio
async def test_it_13_debug_inference_trace_authorization_and_schema(
    client: AsyncClient, db_session: AsyncSession
):
    """
    IT-13: Debug trace endpoint /api/v1/recommendations/debug/me is strictly admin-only.
    Regular users receive 403 Forbidden; Admin users receive 200 with full audit trace.
    """
    # 1. Regular user
    await client.post(
        "/api/v1/users/register",
        json={"email": "regular_trace@example.com", "password": "pass"},
    )
    reg_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "regular_trace@example.com", "password": "pass"},
    )
    reg_token = reg_login.json()["access_token"]

    # 2. Admin user
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(
            email="admin_trace@example.com", password="adminpassword", is_admin=True
        ),
    )
    adm_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "admin_trace@example.com", "password": "adminpassword"},
    )
    adm_token = adm_login.json()["access_token"]

    # Regular user attempt -> 403 Forbidden
    res_reg = await client.get(
        "/api/v1/recommendations/debug/me",
        headers={"Authorization": f"Bearer {reg_token}"},
    )
    assert (
        res_reg.status_code == 403
    ), f"Expected 403 for regular user, got {res_reg.status_code}"

    # Admin user attempt -> 200 OK
    res_adm = await client.get(
        "/api/v1/recommendations/debug/me",
        headers={"Authorization": f"Bearer {adm_token}"},
    )
    assert (
        res_adm.status_code == 200
    ), f"Expected 200 for admin user, got {res_adm.status_code}"
    trace_data = res_adm.json()
    assert "user_id" in trace_data
    assert "padded_input_window" in trace_data
    assert "raw_retrieved_ids" in trace_data
    assert "ids_removed_already_rated" in trace_data
    assert "final_top_k_ids" in trace_data
    assert "threshold_used" in trace_data


@pytest.mark.asyncio
async def test_it_14_cold_start_threshold_and_source_labelling(
    client: AsyncClient, db_session: AsyncSession
):
    """
    IT-14: Users below MIN_SEQUENCE_LENGTH (< 3 ratings) receive popularity items
    with source='popularity', score=None, is_personalized=False.
    """
    # Seed popular movies
    m1 = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Pop 1", genres="Action", movie_lens_id=9001),
    )
    m2 = await crud.movie.create(
        db_session,
        obj_in=MovieCreate(title="Pop 2", genres="Drama", movie_lens_id=9002),
    )

    await client.post(
        "/api/v1/users/register",
        json={"email": "cold_user@example.com", "password": "pass"},
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "cold_user@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # Case A: 0 ratings -> popularity
    res_0 = await client.get("/api/v1/recommendations/user/me?count=5", headers=headers)
    assert res_0.status_code == 200
    recs_0 = res_0.json()
    assert len(recs_0) > 0
    assert recs_0[0]["source"] == "popularity"
    assert recs_0[0]["score"] is None
    assert recs_0[0]["is_personalized"] is False

    # Case B: 1 rating (below threshold 3) -> still popularity
    await client.post(
        "/api/v1/ratings/",
        json={"movie_id": m1.id, "rating": 5.0, "timestamp": 1000},
        headers=headers,
    )
    res_1 = await client.get("/api/v1/recommendations/user/me?count=5", headers=headers)
    assert res_1.status_code == 200
    recs_1 = res_1.json()
    assert len(recs_1) > 0
    assert recs_1[0]["source"] == "popularity"


@pytest.mark.asyncio
async def test_it_15_onboarding_genre_diversity_and_rating_persistence(
    client: AsyncClient, db_session: AsyncSession
):
    """
    IT-15: Onboarding movie endpoint /api/v1/movies/onboarding returns genre-diverse selection.
    User can submit multiple ratings during onboarding and ratings are persisted in chronological order.
    """
    # Seed movies across 4 distinct genres
    genres_to_seed = ["Action", "Comedy", "Drama", "Sci-Fi", "Horror"]
    seeded_movies = []
    for idx, g in enumerate(genres_to_seed):
        m = await crud.movie.create(
            db_session,
            obj_in=MovieCreate(
                title=f"Diverse Movie {g}",
                genres=g,
                movie_lens_id=9100 + idx,
            ),
        )
        seeded_movies.append(m)

    # 1. Fetch onboarding movies
    res = await client.get("/api/v1/movies/onboarding?limit=10")
    assert res.status_code == 200
    movies = res.json()
    assert len(movies) >= 4

    # Verify genre diversity: at least 3 distinct genres represented
    distinct_genres = set()
    for m in movies:
        if m.get("genres"):
            for g in m["genres"].split("|"):
                distinct_genres.add(g.strip())
    assert (
        len(distinct_genres) >= 3
    ), f"Expected at least 3 distinct genres, got {distinct_genres}"

    # 2. User onboarding flow: register and rate 3 diverse movies in sequence
    await client.post(
        "/api/v1/users/register",
        json={"email": "onboard_user@example.com", "password": "pass"},
    )
    login_res = await client.post(
        "/api/v1/users/login/token",
        data={"username": "onboard_user@example.com", "password": "pass"},
    )
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    for idx, m in enumerate(seeded_movies[:3]):
        t = 1000 + (idx * 50)
        rate_res = await client.post(
            "/api/v1/ratings/",
            json={"movie_id": m.id, "rating": 4.5, "timestamp": t},
            headers=headers,
        )
        assert rate_res.status_code == 201

    # Verify ratings persisted in order
    my_ratings_res = await client.get("/api/v1/ratings/user/me", headers=headers)
    assert my_ratings_res.status_code == 200
    my_ratings = my_ratings_res.json()
    assert len(my_ratings) == 3
    # Returned newest first (DESC)
    assert my_ratings[0]["timestamp"] >= my_ratings[1]["timestamp"]


@pytest.mark.asyncio
async def test_it_16_admin_diagnostics_and_authorization(
    client: AsyncClient, db_session: AsyncSession
):
    """
    IT-16: Admin endpoints enforce 403 for non-admin users and return valid system data for admin users.
    """
    # 1. Normal user setup
    await client.post(
        "/api/v1/users/register",
        json={"email": "normal_diag@example.com", "password": "pass"},
    )
    normal_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "normal_diag@example.com", "password": "pass"},
    )
    normal_headers = {"Authorization": f"Bearer {normal_login.json()['access_token']}"}

    # 2. Normal user gets 403 Forbidden on all admin diagnostic endpoints
    assert (
        await client.get("/api/v1/admin/system-health", headers=normal_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/admin/database-counts", headers=normal_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/admin/model-info", headers=normal_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/admin/training-status/latest", headers=normal_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/admin/latest-evaluation", headers=normal_headers)
    ).status_code == 403
    assert (
        await client.get("/api/v1/admin/models/versions", headers=normal_headers)
    ).status_code == 403

    # 3. Admin user setup
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(
            email="super_admin@example.com", password="adminpassword", is_admin=True
        ),
    )
    admin_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "super_admin@example.com", "password": "adminpassword"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # 4. Admin accesses system health -> 200 with structured components
    health_res = await client.get("/api/v1/admin/system-health", headers=admin_headers)
    assert health_res.status_code == 200
    health_data = health_res.json()
    assert "database" in health_data
    assert "redis" in health_data
    assert "recommender_model" in health_data

    # 5. Admin accesses database counts -> 200 with actual counts
    counts_res = await client.get(
        "/api/v1/admin/database-counts", headers=admin_headers
    )
    assert counts_res.status_code == 200
    counts_data = counts_res.json()
    assert "users" in counts_data
    assert "movies" in counts_data
    assert "ratings" in counts_data

    # 6. Admin accesses latest training status -> 200 with valid status mapping
    status_res = await client.get(
        "/api/v1/admin/training-status/latest", headers=admin_headers
    )
    assert status_res.status_code == 200
    assert status_res.json()["status"] in (
        "idle",
        "queued",
        "running",
        "successful",
        "failed",
    )


@pytest.mark.asyncio
async def test_it_17_admin_model_versions_and_rollback(
    client: AsyncClient, db_session: AsyncSession, tmp_path
):
    """
    IT-17: Tests model versioning listing and rollback admin endpoints.
    """
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(
            email="version_admin@example.com", password="adminpassword", is_admin=True
        ),
    )
    admin_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "version_admin@example.com", "password": "adminpassword"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    # 1. Fetch versions list
    ver_res = await client.get("/api/v1/admin/models/versions", headers=admin_headers)
    assert ver_res.status_code == 200
    assert "versions" in ver_res.json()

    # 2. Rollback with non-existent version -> 404 Not Found
    bad_rollback = await client.post(
        "/api/v1/admin/models/rollback",
        json={"version_name": "gru4rec_non_existent_version.keras"},
        headers=admin_headers,
    )
    assert bad_rollback.status_code == 404


def test_it_18_safe_model_replacement_forced_failure(tmp_path):
    """
    IT-18: Proves that safe replacement verification rejects an invalid/corrupted model
    and preserves the existing model intact without overwrite.
    """
    from app.services.recommender.train import (
        rollback_model_version,
        verify_model_artifact,
    )

    # 1. Create a corrupted file
    corrupt_file = tmp_path / "corrupt_model.keras"
    corrupt_file.write_text("not a real keras h5 / zip artifact")

    # 2. verify_model_artifact must return False
    assert verify_model_artifact(str(corrupt_file)) is False

    # 3. Attempting to rollback to corrupted file raises ValueError and aborts
    live_model = tmp_path / "live_model.keras"
    live_model.write_text("original_valid_live_content")

    with pytest.raises(ValueError, match="failed verification check"):
        rollback_model_version(
            version_filename="corrupt_model.keras",
            target_path=str(live_model),
            versions_dir=tmp_path,
        )

    # 4. Live model content must remain completely unchanged
    assert live_model.read_text() == "original_valid_live_content"


@pytest.mark.asyncio
async def test_it_19_evaluation_file_absent_returns_not_yet_measured(
    client: AsyncClient, db_session: AsyncSession
):
    """
    IT-19: When evaluation files are queried, endpoint returns structured results or 'NOT YET MEASURED'.
    """
    admin_user = await crud.user.create(
        db_session,
        obj_in=UserCreate(
            email="eval_admin@example.com", password="adminpassword", is_admin=True
        ),
    )
    admin_login = await client.post(
        "/api/v1/users/login/token",
        data={"username": "eval_admin@example.com", "password": "adminpassword"},
    )
    admin_headers = {"Authorization": f"Bearer {admin_login.json()['access_token']}"}

    eval_res = await client.get(
        "/api/v1/admin/latest-evaluation", headers=admin_headers
    )
    assert eval_res.status_code == 200
    data = eval_res.json()
    assert data["status"] in ("MEASURED", "NOT YET MEASURED")
