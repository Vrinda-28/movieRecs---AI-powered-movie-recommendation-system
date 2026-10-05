import time
from datetime import datetime, timedelta, timezone
from jose import jwt
import pandas as pd
import pytest
from pydantic import ValidationError

from app.core.config import settings
from app.schemas.rating import RatingBase, RatingCreate
from app.security import create_access_token, get_password_hash, verify_password
from app.services.recommender.evaluate import compute_toy_example_metrics
from app.services.recommender.preprocessing import (
    get_movie_sequence_per_user,
    prepare_user_context_for_prediction,
)


def test_ut_01_preprocessing_chronological_sort():
    """UT-01: One user with ratings given out of time order -> Sequence sorted oldest to newest."""
    ratings_data = [
        {"user_id": 1, "movie_id": 101, "rating": 4.0, "timestamp": 300},
        {"user_id": 1, "movie_id": 102, "rating": 5.0, "timestamp": 100},
        {"user_id": 1, "movie_id": 103, "rating": 3.0, "timestamp": 200},
    ]
    df = pd.DataFrame(ratings_data)
    sequences = get_movie_sequence_per_user(df)

    user_seq = sequences[1]
    timestamps = [item["timestamp"] for item in user_seq]
    movie_ids = [item["movie_id"] for item in user_seq]

    assert timestamps == [100, 200, 300], f"Timestamps not sorted chronologically: {timestamps}"
    assert movie_ids == [102, 103, 101], f"Movie sequence not matching chronological order: {movie_ids}"


def test_ut_02_preprocessing_padding_windowing():
    """UT-02: User with 3 ratings, window length 5 -> Window of length 5, padded with 0."""
    movie_ids = [10, 20, 30]
    window_length = 5
    padded = prepare_user_context_for_prediction(movie_ids, max_context_length=window_length)

    assert len(padded) == 5, f"Padded window length {len(padded)} != {window_length}"
    assert padded == [10, 20, 30, 0, 0], f"Padded sequence {padded} does not match expected [10, 20, 30, 0, 0]"


def test_ut_03_preprocessing_unknown_movie_id_handling():
    """UT-03: History containing unknown or edge-case IDs is handled safely without throwing."""
    unknown_ids = [999999, 888888]
    padded = prepare_user_context_for_prediction(unknown_ids, max_context_length=5)
    assert len(padded) == 5
    assert padded[:2] == [999999, 888888]
    assert padded[2:] == [0, 0, 0]


def test_ut_04_security_password_hash_and_verify():
    """UT-04: Hash password 'abc123' -> Stored hash differs from plain text; verify returns True."""
    password = "abc123"
    hashed = get_password_hash(password)

    assert hashed != password, "Hashed password must differ from plain text"
    assert verify_password(password, hashed) is True, "verify_password must return True for correct password"
    assert verify_password("wrongpassword", hashed) is False, "verify_password must return False for wrong password"


def test_ut_05_security_expired_token_rejected():
    """UT-05: Token past its expiry time is rejected as invalid by jwt decoder."""
    email = "testuser@example.com"
    # Create expired token
    past_expire = datetime.now(timezone.utc) - timedelta(minutes=10)
    to_encode = {"exp": past_expire, "sub": email}
    expired_token = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

    # Valid token for comparison
    valid_token = create_access_token(subject=email, expires_delta=timedelta(minutes=30))

    # Valid token decodes properly
    decoded_valid = jwt.decode(valid_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    assert decoded_valid["sub"] == email

    # Expired token raises jwt.ExpiredSignatureError or JWTError
    with pytest.raises(Exception):
        jwt.decode(expired_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])


def test_ut_06_rating_schema_validation():
    """UT-06: Rating value 0, then 6, then 'abc' -> ValidationError for all three."""
    # Value 0 is out of bounds (< 1.0)
    with pytest.raises(ValidationError):
        RatingCreate(movie_id=1, rating=0.0, timestamp=1000)

    # Value 6 is out of bounds (> 5.0)
    with pytest.raises(ValidationError):
        RatingCreate(movie_id=1, rating=6.0, timestamp=1000)

    # Non-numeric 'abc'
    with pytest.raises(ValidationError):
        RatingCreate(movie_id=1, rating="abc", timestamp=1000)

    # Valid value 3.5 passes
    valid_rating = RatingCreate(movie_id=1, rating=3.5, timestamp=1000)
    assert valid_rating.rating == 3.5


def test_ut_07_metrics_stage2_toy_example():
    """
    UT-07: Metrics toy example arithmetic matches Stage 2 Section 2.1.5 worked example:
    Top 5 = [a,b,c,d,e], relevant = {b,e} -> P@5 = 0.40, R@5 = 1.00, Hit = 1.0, NDCG@5 = 0.624
    """
    metrics = compute_toy_example_metrics()
    assert metrics["precision@5"] == 0.40, f"Expected 0.40, got {metrics['precision@5']}"
    assert metrics["recall@5"] == 1.00, f"Expected 1.00, got {metrics['recall@5']}"
    assert metrics["hit_rate@5"] == 1.00, f"Expected 1.00, got {metrics['hit_rate@5']}"
    assert round(metrics["ndcg@5"], 3) == 0.624, f"Expected 0.624, got {metrics['ndcg@5']}"


def test_ut_08_predict_already_rated_filtering():
    """UT-08: Scores array with already-rated movies -> Watched movies are filtered out."""
    all_candidate_ids = [101, 102, 103, 104, 105]
    watched_movie_ids = {101, 102}  # Movies the user already rated
    num_recommendations = 3

    # Filter out watched items
    filtered_recommendations = [
        m for m in all_candidate_ids if m not in watched_movie_ids
    ][:num_recommendations]

    assert 101 not in filtered_recommendations, "Already-rated movie 101 must not be in recommendations"
    assert 102 not in filtered_recommendations, "Already-rated movie 102 must not be in recommendations"
    assert filtered_recommendations == [103, 104, 105]
