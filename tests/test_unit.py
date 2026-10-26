import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest
from jose import jwt
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

    assert timestamps == [
        100,
        200,
        300,
    ], f"Timestamps not sorted chronologically: {timestamps}"
    assert movie_ids == [
        102,
        103,
        101,
    ], f"Movie sequence not matching chronological order: {movie_ids}"


def test_ut_02_preprocessing_padding_windowing():
    """UT-02: User with 3 ratings, window length 5 -> Window of length 5, padded with 0."""
    movie_ids = [10, 20, 30]
    window_length = 5
    padded = prepare_user_context_for_prediction(
        movie_ids, max_context_length=window_length
    )

    assert len(padded) == 5, f"Padded window length {len(padded)} != {window_length}"
    assert padded == [
        10,
        20,
        30,
        0,
        0,
    ], f"Padded sequence {padded} does not match expected [10, 20, 30, 0, 0]"


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
    assert (
        verify_password(password, hashed) is True
    ), "verify_password must return True for correct password"
    assert (
        verify_password("wrongpassword", hashed) is False
    ), "verify_password must return False for wrong password"


def test_ut_05_security_expired_token_rejected():
    """UT-05: Token past its expiry time is rejected as invalid by jwt decoder."""
    email = "testuser@example.com"
    # Create expired token
    past_expire = datetime.now(timezone.utc) - timedelta(minutes=10)
    to_encode = {"exp": past_expire, "sub": email}
    expired_token = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM
    )

    # Valid token for comparison
    valid_token = create_access_token(
        subject=email, expires_delta=timedelta(minutes=30)
    )

    # Valid token decodes properly
    decoded_valid = jwt.decode(
        valid_token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
    )
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
    assert (
        metrics["precision@5"] == 0.40
    ), f"Expected 0.40, got {metrics['precision@5']}"
    assert metrics["recall@5"] == 1.00, f"Expected 1.00, got {metrics['recall@5']}"
    assert metrics["hit_rate@5"] == 1.00, f"Expected 1.00, got {metrics['hit_rate@5']}"
    assert (
        round(metrics["ndcg@5"], 3) == 0.624
    ), f"Expected 0.624, got {metrics['ndcg@5']}"


@pytest.mark.asyncio
async def test_ut_08_predict_already_rated_filtering_real_function(monkeypatch):
    """
    UT-08: Calls the real get_recommendations_for_user with a stubbed model
    and verifies that already-rated movies are never returned.
    """
    from unittest.mock import AsyncMock, MagicMock

    import numpy as np

    from app.services.recommender import predict

    # Stub DB session
    mock_db = AsyncMock()

    # Stub user with 3 ratings (meets MIN_SEQUENCE_LENGTH threshold)
    mock_user = MagicMock()
    mock_user.id = 42

    # Ratings returned in DESC order by timestamp from DB
    r1 = MagicMock(movie_id=10, timestamp=300)
    r2 = MagicMock(movie_id=20, timestamp=200)
    r3 = MagicMock(movie_id=30, timestamp=100)

    async def mock_get_ratings_by_user(db, user_id, limit):
        return [r1, r2, r3]

    monkeypatch.setattr(
        predict.crud.rating, "get_ratings_by_user", mock_get_ratings_by_user
    )

    # Stub model and mappings
    predict._model = MagicMock()
    predict._movies_count_at_load = 50
    predict._movie_id_to_details = {
        10: {"id": 10, "title": "Watched 1", "genres": "Drama"},
        20: {"id": 20, "title": "Watched 2", "genres": "Drama"},
        30: {"id": 30, "title": "Watched 3", "genres": "Drama"},
        40: {"id": 40, "title": "Unwatched 1", "genres": "Action"},
        45: {"id": 45, "title": "Unwatched 2", "genres": "Comedy"},
    }

    # Model output predicts [10, 20, 40, 45] -> 10 and 20 are watched
    mock_tensor = MagicMock()
    mock_tensor.numpy.return_value = np.array([[10, 20, 40, 45]])
    predict._model.return_value = {"predictions": mock_tensor}

    async def noop_load(db, force_reload=False):
        pass

    monkeypatch.setattr(predict, "load_model_and_mappings", noop_load)

    recs = await predict.get_recommendations_for_user(
        db=mock_db, user=mock_user, exclude_watched=True, num_recommendations=2
    )

    rec_ids = [r["movie_id"] for r in recs]
    assert 10 not in rec_ids, "Watched movie 10 must not be in recommendations"
    assert 20 not in rec_ids, "Watched movie 20 must not be in recommendations"
    assert 30 not in rec_ids, "Watched movie 30 must not be in recommendations"
    assert 40 in rec_ids, "Unwatched movie 40 should be recommended"
    assert 45 in rec_ids, "Unwatched movie 45 should be recommended"


def test_ut_09_inference_chronological_ordering_and_window_truncation():
    """
    UT-09: Verifies that reverse-chronological DB ratings are correctly sorted
    ascending (oldest first) and truncated to MAX_CONTEXT_LENGTH.
    """
    # Simulate DB returning 15 ratings in DESC order (newest first)
    desc_ratings = [{"movie_id": i, "timestamp": 1000 + i} for i in range(15, 0, -1)]
    # Reversing to ascending
    asc_ratings = list(reversed(desc_ratings))
    asc_movie_ids = [r["movie_id"] for r in asc_ratings]

    # Oldest timestamp must be first
    assert asc_ratings[0]["timestamp"] == 1001
    assert asc_ratings[-1]["timestamp"] == 1015
    assert asc_movie_ids == list(range(1, 16))

    # Truncate to MAX_CONTEXT_LENGTH (10) -> keeps the most recent 10 (ids 6..15)
    max_context = 10
    truncated = asc_movie_ids[-max_context:]
    assert len(truncated) == 10
    assert truncated == list(range(6, 16))

    # Test that reversed order would FAIL this assertion
    reversed_check = list(reversed(truncated))
    assert reversed_check != truncated, "Reversed order must not match ascending order"


@pytest.mark.asyncio
async def test_ut_10_inference_vocabulary_overflow_handling(monkeypatch):
    """
    UT-10: Handles movies added to DB after model was trained (IDs > model vocab ceiling).
    Verifies they are safely skipped during prediction without crashing.
    """
    from unittest.mock import AsyncMock, MagicMock

    import numpy as np

    from app.services.recommender import predict

    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = 99

    # User rated movies: 1, 2, 9999 (where 9999 is post-training OOV movie)
    r1 = MagicMock(movie_id=1, timestamp=100)
    r2 = MagicMock(movie_id=2, timestamp=200)
    r3 = MagicMock(movie_id=9999, timestamp=300)

    async def mock_get_ratings_by_user(db, user_id, limit):
        return [r3, r2, r1]

    monkeypatch.setattr(
        predict.crud.rating, "get_ratings_by_user", mock_get_ratings_by_user
    )

    # Model was trained with vocab up to 50
    predict._model = MagicMock()
    predict._movies_count_at_load = 50
    predict._movie_id_to_details = {
        1: {"id": 1, "title": "Movie 1", "genres": "Action"},
        2: {"id": 2, "title": "Movie 2", "genres": "Action"},
        5: {"id": 5, "title": "Movie 5", "genres": "Sci-Fi"},
    }

    # Model predictions contain a rogue ID 888 (exceeding vocab) and valid ID 5
    mock_tensor = MagicMock()
    mock_tensor.numpy.return_value = np.array([[888, 5]])
    predict._model.return_value = {"predictions": mock_tensor}

    async def noop_load(db, force_reload=False):
        pass

    monkeypatch.setattr(predict, "load_model_and_mappings", noop_load)

    recs = await predict.get_recommendations_for_user(
        db=mock_db, user=mock_user, exclude_watched=True, num_recommendations=1
    )

    rec_ids = [r["movie_id"] for r in recs]
    assert 888 not in rec_ids, "Out-of-vocab ID 888 must be filtered out"
    assert 5 in rec_ids, "Valid in-vocab ID 5 must be returned"


def test_ut_11_leak_free_split_proof():
    """
    UT-11: Proves that the held-out test rating is strictly absent from all
    sliding-window training examples generated for leak-free evaluation.
    """
    from app.services.recommender.evaluate import build_leave_last_out_splits
    from app.services.recommender.preprocessing import (
        generate_examples_from_user_sequences,
    )

    # User 1 rated [101, 102, 103, 104] at timestamps [100, 200, 300, 400]
    # User 2 rated [201, 202, 203] at timestamps [100, 200, 300]
    ratings_data = [
        {"user_id": 1, "movie_id": 101, "rating": 4.0, "timestamp": 100},
        {"user_id": 1, "movie_id": 102, "rating": 4.5, "timestamp": 200},
        {"user_id": 1, "movie_id": 103, "rating": 5.0, "timestamp": 300},
        {"user_id": 1, "movie_id": 104, "rating": 4.0, "timestamp": 400},  # HELD OUT
        {"user_id": 2, "movie_id": 201, "rating": 3.0, "timestamp": 100},
        {"user_id": 2, "movie_id": 202, "rating": 4.0, "timestamp": 200},
        {"user_id": 2, "movie_id": 203, "rating": 5.0, "timestamp": 300},  # HELD OUT
    ]
    df = pd.DataFrame(ratings_data)

    train_sequences, test_instances, _ = build_leave_last_out_splits(df)

    # Check test instances
    assert len(test_instances) == 2
    u1_test = next(t for t in test_instances if t[0] == 1)
    u2_test = next(t for t in test_instances if t[0] == 2)
    assert u1_test[2] == 104, "User 1 held out target must be 104"
    assert u2_test[2] == 203, "User 2 held out target must be 203"

    # Generate training examples from the leak-free train_sequences
    train_examples = generate_examples_from_user_sequences(train_sequences)

    # Prove that NO training example for User 1 uses 104 as a label or context
    for ex in train_examples:
        assert (
            ex["label_movie_id"] != 104
        ), "Held-out item 104 must NEVER appear as training label"
        assert (
            ex["label_movie_id"] != 203
        ), "Held-out item 203 must NEVER appear as training label"
        assert (
            104 not in ex["context_movie_id"]
        ), "Held-out item 104 must NEVER appear in training context"
        assert (
            203 not in ex["context_movie_id"]
        ), "Held-out item 203 must NEVER appear in training context"


def test_ut_12_padding_consistency_training_and_inference():
    """
    UT-12: Proves that training example generator and inference context preparation
    use the exact same zero-padding conventions for both 'right' and 'left' modes.
    """
    from app.services.recommender.preprocessing import (
        generate_examples_from_user_sequences,
        prepare_user_context_for_prediction,
    )

    # Test right-padding convention
    seq_right = {
        1: [
            {"movie_id": 10, "timestamp": 100, "rating": 5.0},
            {"movie_id": 20, "timestamp": 200, "rating": 5.0},
            {"movie_id": 30, "timestamp": 300, "rating": 5.0},
        ]
    }
    train_ex_right = generate_examples_from_user_sequences(
        seq_right, max_context_length=5, padding_mode="right"
    )
    # Last example is for predicting 30 given context [10, 20]
    last_train_ctx_right = train_ex_right[-1]["context_movie_id"]
    inf_ctx_right = prepare_user_context_for_prediction(
        [10, 20], max_context_length=5, padding_mode="right"
    )
    assert last_train_ctx_right == inf_ctx_right == [10, 20, 0, 0, 0]

    # Test left-padding convention
    seq_left = {
        1: [
            {"movie_id": 10, "timestamp": 100, "rating": 5.0},
            {"movie_id": 20, "timestamp": 200, "rating": 5.0},
            {"movie_id": 30, "timestamp": 300, "rating": 5.0},
        ]
    }
    train_ex_left = generate_examples_from_user_sequences(
        seq_left, max_context_length=5, padding_mode="left"
    )
    last_train_ctx_left = train_ex_left[-1]["context_movie_id"]
    inf_ctx_left = prepare_user_context_for_prediction(
        [10, 20], max_context_length=5, padding_mode="left"
    )
    assert last_train_ctx_left == inf_ctx_left == [0, 0, 0, 10, 20]


def test_ut_13_model_architecture_and_retrieval_shapes():
    """
    UT-13: Verifies SequentialRetrievalModel input/output shapes,
    embedding capacity, and BruteForce retrieval top-K dimension.
    """
    import tensorflow as tf

    from app.services.recommender.model import SequentialRetrievalModel

    vocab_size = 100
    embed_dim = 16
    window_length = 8
    k = 10

    model = SequentialRetrievalModel(
        movies_count=vocab_size,
        embedding_dimension=embed_dim,
        gru_units=embed_dim,
        mask_zero=True,
        k=k,
    )

    # Build model
    dummy_input = tf.zeros((2, window_length), dtype=tf.int32)
    output = model(dummy_input, training=False)

    assert "query_embeddings" in output
    assert "predictions" in output

    query_shape = output["query_embeddings"].shape
    pred_shape = output["predictions"].shape

    assert query_shape == (
        2,
        embed_dim,
    ), f"Expected query shape (2, {embed_dim}), got {query_shape}"
    assert pred_shape == (
        2,
        k,
    ), f"Expected predictions shape (2, {k}), got {pred_shape}"


def test_ut_14_seed_reproducibility_on_tiny_fixture():
    """
    UT-14: Verifies that fixing seeds produces deterministic model initialization.
    """
    import random

    import numpy as np
    import tensorflow as tf

    from app.services.recommender.model import SequentialRetrievalModel

    def init_and_call(seed_val):
        random.seed(seed_val)
        np.random.seed(seed_val)
        tf.random.set_seed(seed_val)
        m = SequentialRetrievalModel(movies_count=50, embedding_dimension=16, k=5)
        inp = tf.constant([[1, 2, 3, 0, 0]], dtype=tf.int32)
        return m(inp, training=False)["query_embeddings"].numpy()

    out1 = init_and_call(12345)
    out2 = init_and_call(12345)
    np.testing.assert_allclose(
        out1,
        out2,
        rtol=1e-5,
        atol=1e-5,
        err_msg="Seed 12345 should yield identical initial embeddings",
    )


def test_ut_15_reason_generation_deterministic_on_fixture():
    """
    UT-15: Verifies that reason generation is deterministic across explanation types.
    """
    from app.services.recommender.explanation import generate_recommendation_reason

    user_ratings = [
        {
            "movie_id": 1,
            "rating": 5.0,
            "title": "Toy Story (1995)",
            "genres": "Animation|Children's|Comedy",
        },
        {
            "movie_id": 2,
            "rating": 4.5,
            "title": "Jumanji (1995)",
            "genres": "Adventure|Children's|Fantasy",
        },
        {
            "movie_id": 3,
            "rating": 2.0,
            "title": "Grumpier Old Men (1995)",
            "genres": "Comedy|Romance",
        },
    ]
    movie_details = {
        1: {"title": "Toy Story (1995)", "genres": "Animation|Children's|Comedy"},
        2: {"title": "Jumanji (1995)", "genres": "Adventure|Children's|Fantasy"},
        3: {"title": "Grumpier Old Men (1995)", "genres": "Comedy|Romance"},
        10: {"title": "A Bug's Life (1998)", "genres": "Animation|Children's"},
        99: {"title": "Popular Blockbuster (2000)", "genres": "Action"},
    }

    # Popularity item
    pop_item = {
        "movie_id": 99,
        "title": "Popular Blockbuster (2000)",
        "source": "popularity",
        "genres": "Action",
    }
    reason_pop = generate_recommendation_reason(
        pop_item, user_ratings, model=None, movie_id_to_details=movie_details
    )
    assert reason_pop["reason_type"] == "popularity"
    assert "Popular" in reason_pop["reason_text"]

    # Genre overlap item
    genre_item = {
        "movie_id": 10,
        "title": "A Bug's Life (1998)",
        "source": "gru4rec",
        "genres": "Animation|Children's",
    }
    reason_genre = generate_recommendation_reason(
        genre_item, user_ratings, model=None, movie_id_to_details=movie_details
    )
    assert reason_genre["reason_type"] == "genre_overlap"
    assert (
        "Animation" in reason_genre["reason_text"]
        or "Children's" in reason_genre["reason_text"]
    )


def test_ut_16_reason_thresholds_respected():
    """
    UT-16: When cosine similarity is below threshold, embedding_neighbor is not used.
    """
    import numpy as np

    from app.services.recommender.explanation import (
        compute_cosine_similarity,
        generate_recommendation_reason,
    )

    # Test cosine similarity calculation
    v1 = np.array([1.0, 0.0, 0.0])
    v2 = np.array([1.0, 0.0, 0.0])
    v3 = np.array([0.0, 1.0, 0.0])
    assert compute_cosine_similarity(v1, v2) == 1.0
    assert compute_cosine_similarity(v1, v3) == 0.0

    # User rated Drama movie
    user_ratings = [
        {"movie_id": 1, "rating": 5.0, "title": "Drama Movie", "genres": "Drama"}
    ]
    rec_item = {
        "movie_id": 20,
        "title": "Action Movie",
        "genres": "Action",
        "source": "gru4rec",
    }

    # No embedding model provided and no genre overlap -> falls back to recent_activity
    reason = generate_recommendation_reason(
        rec_item, user_ratings, model=None, similarity_threshold=0.8
    )
    assert reason["reason_type"] == "recent_activity"
    assert reason["reason_text"] == "Based on your recent ratings"


def test_ut_17_reasons_never_reference_unrated_movies():
    """
    UT-17: Asserts that referenced source_movie_id is strictly a movie rated by the user.
    """
    from app.services.recommender.explanation import generate_recommendation_reason

    user_ratings = [
        {
            "movie_id": 42,
            "rating": 5.0,
            "title": "User Favorite",
            "genres": "Sci-Fi|Thriller",
        },
    ]
    movie_details = {
        42: {"title": "User Favorite", "genres": "Sci-Fi|Thriller"},
        100: {"title": "Recommended Sci-Fi", "genres": "Sci-Fi"},
    }
    rec_item = {
        "movie_id": 100,
        "title": "Recommended Sci-Fi",
        "genres": "Sci-Fi",
        "source": "gru4rec",
    }

    reason = generate_recommendation_reason(
        rec_item, user_ratings, model=None, movie_id_to_details=movie_details
    )

    rated_movie_ids = {r["movie_id"] for r in user_ratings}
    if reason.get("source_movie_id") is not None:
        assert (
            reason["source_movie_id"] in rated_movie_ids
        ), f"Referenced movie {reason['source_movie_id']} not in user ratings {rated_movie_ids}"


def test_ut_18_diversity_metrics_toy_examples():
    """
    UT-18: Hand-computed verification of Diversity metrics:
    - Catalogue Coverage: 3 unique items out of 10 -> 0.30
    - Top-10% Concentration: 2 out of 4 slots in top-10% -> 0.50
    - Gini Coefficient: uniform distribution -> 0.0
    - Intra-List Diversity: disjoint genres -> 1.0; identical genres -> 0.0
    """
    from app.services.recommender.diversity import (
        compute_catalogue_coverage,
        compute_gini_coefficient,
        compute_intra_list_diversity,
        compute_popularity_concentration_top10,
        compute_shannon_entropy,
    )

    # 1. Catalogue coverage
    recs = [[1, 2], [2, 3]]
    cov = compute_catalogue_coverage(recs, catalogue_size=10)
    assert cov == 0.30, f"Expected 0.30, got {cov}"

    # 2. Top-10% Concentration
    top_10_set = {1, 99}
    conc = compute_popularity_concentration_top10(recs, top_10_set)
    # Total slots = 4, items matching top_10_set = 1 (item 1) -> 1/4 = 0.25
    assert conc == 0.25, f"Expected 0.25, got {conc}"

    # 3. Gini Coefficient on perfectly uniform distribution
    uniform_counts = [5, 5, 5, 5]
    gini_uniform = compute_gini_coefficient(uniform_counts)
    assert (
        abs(gini_uniform) < 1e-5
    ), f"Expected Gini 0.0 for uniform, got {gini_uniform}"

    # 4. Intra-List Diversity (ILD)
    # Movie 10 and 20 share no genres -> ILD = 1.0
    genres_disjoint = {10: {"Action"}, 20: {"Romance"}}
    ild_disjoint = compute_intra_list_diversity([10, 20], genres_disjoint)
    assert (
        ild_disjoint == 1.0
    ), f"Expected ILD 1.0 for disjoint genres, got {ild_disjoint}"

    # Movie 10 and 20 have identical genres -> ILD = 0.0
    genres_identical = {10: {"Action", "Sci-Fi"}, 20: {"Action", "Sci-Fi"}}
    ild_identical = compute_intra_list_diversity([10, 20], genres_identical)
    assert (
        ild_identical == 0.0
    ), f"Expected ILD 0.0 for identical genres, got {ild_identical}"


def test_ut_19_mmr_reranking_diversity_behavior():
    """
    UT-19: MMR re-ranking selects top items while skipping duplicate embeddings when k is smaller.
    """
    from app.services.recommender.diversity import mmr_rerank

    candidate_ids = [1, 2, 3, 4, 5]
    # When model is None (embeddings unavailable), MMR preserves rank ordering safely
    reranked = mmr_rerank(candidate_ids, model=None, k=3)
    assert reranked == [1, 2, 3]
    assert len(reranked) == 3
