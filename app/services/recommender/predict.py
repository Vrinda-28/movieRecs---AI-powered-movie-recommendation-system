"""
Inference pipeline for GRU4Rec sequential recommendation.

Full documented flow:
  1. HISTORY      – fetch user's Rating rows ordered DESC by timestamp (raw DB order)
  2. CHRONOLOGICAL – reverse to ascending timestamp order (oldest → newest)
  3. TRUNCATE     – keep the last MAX_CONTEXT_LENGTH items (most-recent context window)
  4. FILTER OOV   – drop any movie_id > movies_count_at_load (added after model training)
  5. PREPROCESS   – prepare_user_context_for_prediction: right-pad with 0 to MAX_CONTEXT_LENGTH
  6. MODEL INPUT  – tf.constant of shape (1, MAX_CONTEXT_LENGTH), dtype=int32
  7. RETRIEVAL    – BruteForceRetrieval returns top-K internal movie IDs by dot-product distance
                   (keras_rs.layers.BruteForceRetrieval with return_scores=False → indices only;
                    we cannot expose real dot-product scores without changing BruteForce config;
                    `score` is therefore null in every response item)
  8. FILTER RATED – skip any movie_id already in the user's history (exclude_watched=True)
  9. VOCAB GUARD  – skip any predicted id == 0 (padding) or beyond _movies_count_at_load
 10. RANK / TOP-K – iterate retrieval list in order (already ranked by model); stop at count
 11. BACKFILL     – if fewer than count personalized results, pad with popularity items
 12. RESPONSE     – each item carries:
                      source="gru4rec"    if produced by step 7-10
                      source="popularity" if produced by step 11
                      score=null          (BruteForce returns indices only; fabricating scores
                                           would misrepresent model confidence)
                      is_personalized=True/False mirrors source

Cold-start threshold: users with < MIN_SEQUENCE_LENGTH ratings skip the model entirely
and receive popularity results (source="popularity" on all items).
MIN_SEQUENCE_LENGTH is defined in settings (default 3), matching the training requirement
that sequences must have at least this many interactions to generate training examples.
The threshold for showing model output is MAX_CONTEXT_LENGTH (≥1 usable id in context),
but a meaningful sequence requires ≥ MIN_SEQUENCE_LENGTH ratings.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import keras
import numpy as np
import tensorflow as tf
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud, models
from app.services.recommender.diversity import mmr_rerank
from app.services.recommender.explanation import attach_explanations_to_recommendations
from app.services.recommender.model import SequentialRetrievalModel
from app.services.recommender.preprocessing import prepare_user_context_for_prediction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level model cache (singleton per worker process)
# ---------------------------------------------------------------------------
_model: Optional[SequentialRetrievalModel] = None
_movie_id_to_details: Optional[Dict[int, Dict[str, Any]]] = None
_movies_count_at_load: Optional[int] = (
    None  # max internal Movie.id the model was trained with
)
_loaded_model_timestamp: Optional[float] = None


async def load_model_and_mappings(db: AsyncSession, force_reload: bool = False):
    """Load (or hot-reload) the Keras model and build the in-memory movie-detail cache."""
    global _model, _movie_id_to_details, _movies_count_at_load, _loaded_model_timestamp

    model_path_obj = Path(settings.MODEL_PATH)
    if not model_path_obj.exists():
        logger.warning(
            f"Model file not found at {settings.MODEL_PATH}. Prediction not available."
        )
        _model = None
        _movie_id_to_details = None
        _movies_count_at_load = None
        _loaded_model_timestamp = None
        return

    current_model_timestamp = model_path_obj.stat().st_mtime
    needs_load = (
        force_reload
        or _model is None
        or (
            _loaded_model_timestamp is not None
            and current_model_timestamp > _loaded_model_timestamp
        )
        or _movie_id_to_details is None
    )

    if not needs_load:
        return

    logger.info(
        f"Reloading model/mappings (force={force_reload}, model_none={_model is None}, "
        f"ts_change={_loaded_model_timestamp is None or current_model_timestamp > _loaded_model_timestamp}, "
        f"details_none={_movie_id_to_details is None})."
    )
    _model = None
    _movie_id_to_details = None
    _movies_count_at_load = None
    _loaded_model_timestamp = None

    try:
        _model = keras.models.load_model(
            settings.MODEL_PATH,
            custom_objects={"SequentialRetrievalModel": SequentialRetrievalModel},
        )
        if hasattr(_model, "movies_count"):
            # movies_count is stored in the model config: it is the max internal Movie.id
            # the model vocabulary was built with at training time.
            _movies_count_at_load = _model.movies_count
        else:
            max_id_db = await crud.movie.get_max_internal_movie_id(db)
            _movies_count_at_load = int(max_id_db) if max_id_db else 0
        logger.info(
            f"Model loaded. Vocabulary covers internal movie IDs 1..{_movies_count_at_load}"
        )

        if _movies_count_at_load and _movies_count_at_load > 0:
            # Warm-up call to build the computation graph before first real request
            _model(
                tf.zeros((1, settings.MAX_CONTEXT_LENGTH), dtype=tf.int32),
                training=False,
            )
        _loaded_model_timestamp = current_model_timestamp
        logger.info("Model warm-up complete.")
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        _model = None
        return

    if _movie_id_to_details is None and _model is not None:
        logger.info(
            "Building in-memory movie-detail cache (keyed by internal Movie.id)…"
        )
        all_movies_db = await crud.movie.get_multi(db, limit=10000)
        if not all_movies_db:
            logger.error("No movies found in DB for cache — cache empty.")
            _movie_id_to_details = {}
            return

        _movie_id_to_details = {
            movie.id: {
                "internal_id": movie.id,
                "movie_lens_id": movie.movie_lens_id,
                "title": movie.title,
                "resource_url": movie.resource_url,
                "genres": movie.genres,
            }
            for movie in all_movies_db
        }
        # Reserve slot 0 for padding token
        _movie_id_to_details[0] = {"title": "Padding Token", "internal_id": 0}
        logger.info(f"Movie cache built: {len(_movie_id_to_details) - 1} movies.")


# ---------------------------------------------------------------------------
# Popularity fallback
# ---------------------------------------------------------------------------


async def _get_popularity_fallback(
    db: AsyncSession,
    exclude_movie_ids: Optional[List[int]] = None,
    num_recommendations: int = 10,
) -> List[Dict[str, Any]]:
    """
    Returns popularity-ranked movies for cold-start or model-unavailable scenarios.
    Each item is labelled source='popularity' and score=null.
    """
    popular_movies = await crud.movie.get_most_popular(
        db, limit=num_recommendations, exclude_movie_ids=exclude_movie_ids
    )
    results = []
    for movie in popular_movies:
        results.append(
            {
                "movie_id": movie.id,
                "movie_lens_id": movie.movie_lens_id,
                "title": movie.title,
                "resource_url": movie.resource_url,
                "genres": movie.genres,
                # Truthful labelling: popularity ranking, not GRU4Rec
                "source": "popularity",
                "score": None,  # no meaningful score for popularity rank
                "is_personalized": False,
            }
        )
    return results


# ---------------------------------------------------------------------------
# Main inference function
# ---------------------------------------------------------------------------


async def get_recommendations_for_user(
    db: AsyncSession,
    user: models.User,
    exclude_watched: bool = True,
    num_recommendations: int = 10,
) -> List[Dict[str, Any]]:
    """
    Full documented inference flow (see module docstring for step descriptions).

    Key invariants guaranteed here:
    - History is sorted ascending by timestamp before being fed to the model.
    - Movie IDs beyond the model vocabulary are silently skipped (step 9).
    - Rated movies are never returned when exclude_watched=True (step 8).
    - source='gru4rec' only for model-generated results; source='popularity' for backfill.
    - score=None always (BruteForce returns sorted indices, not raw dot-product scalars).
    """

    # -----------------------------------------------------------------------
    # STEP 1: HISTORY — fetch rating rows from DB (ordered DESC by timestamp)
    # -----------------------------------------------------------------------
    user_ratings_desc = await crud.rating.get_ratings_by_user(
        db, user_id=user.id, limit=settings.MAX_CONTEXT_LENGTH * 2
    )

    # -----------------------------------------------------------------------
    # STEP 2: CHRONOLOGICAL — reverse to ascending timestamp order
    # The DB query returns rows newest-first; the model needs oldest-first.
    # -----------------------------------------------------------------------
    user_ratings_asc = list(reversed(user_ratings_desc))
    user_movie_ids_asc = [r.movie_id for r in user_ratings_asc]

    # -----------------------------------------------------------------------
    # Cold-start check: below MIN_SEQUENCE_LENGTH → skip model, serve popularity
    # Threshold reasoning: MIN_SEQUENCE_LENGTH=3 is the training minimum sequence
    # length. Below it, the user's context window is too sparse to produce meaningful
    # sequential embeddings. We apply the same threshold at inference time for
    # consistency with what the model was trained to handle.
    # -----------------------------------------------------------------------
    if len(user_movie_ids_asc) < settings.MIN_SEQUENCE_LENGTH:
        logger.info(
            f"User {user.id} has {len(user_movie_ids_asc)} ratings "
            f"(threshold={settings.MIN_SEQUENCE_LENGTH}). Serving popularity fallback."
        )
        exclude_ids = user_movie_ids_asc if exclude_watched else []
        fallback = await _get_popularity_fallback(
            db=db,
            exclude_movie_ids=exclude_ids,
            num_recommendations=num_recommendations,
        )
        # Annotate with rating count so frontend can show progress messaging
        for item in fallback:
            item["user_rating_count"] = len(user_movie_ids_asc)
        return attach_explanations_to_recommendations(
            recommendations=fallback,
            user_ratings_asc=user_ratings_asc,
            model=None,
            movie_id_to_details=_movie_id_to_details,
        )

    # -----------------------------------------------------------------------
    # STEP 5-6: Load model, then preprocess and create tensor
    # -----------------------------------------------------------------------
    await load_model_and_mappings(db)
    if not _model or not _movie_id_to_details or _movies_count_at_load is None:
        logger.warning(
            "Model/mappings unavailable. Falling back to popularity recommendations."
        )
        exclude_ids = user_movie_ids_asc if exclude_watched else []
        fallback = await _get_popularity_fallback(
            db=db,
            exclude_movie_ids=exclude_ids,
            num_recommendations=num_recommendations,
        )
        return attach_explanations_to_recommendations(
            recommendations=fallback,
            user_ratings_asc=user_ratings_asc,
            model=None,
            movie_id_to_details=_movie_id_to_details,
        )

    # -----------------------------------------------------------------------
    # STEP 3-4: TRUNCATE to MAX_CONTEXT_LENGTH and FILTER OOV ids
    # OOV = movies added to the DB after the model was trained; their embeddings
    # don't exist in the model vocabulary so they must be excluded from the input.
    # -----------------------------------------------------------------------
    context_ids = user_movie_ids_asc[-settings.MAX_CONTEXT_LENGTH :]
    # Filter out any ID that exceeds the model's vocab (added post-training)
    context_ids_in_vocab = [mid for mid in context_ids if mid <= _movies_count_at_load]
    if not context_ids_in_vocab:
        logger.warning(
            f"User {user.id}: all context IDs exceed model vocab ({_movies_count_at_load}). "
            "Falling back to popularity."
        )
        exclude_ids = user_movie_ids_asc if exclude_watched else []
        fallback = await _get_popularity_fallback(
            db=db,
            exclude_movie_ids=exclude_ids,
            num_recommendations=num_recommendations,
        )
        return attach_explanations_to_recommendations(
            recommendations=fallback,
            user_ratings_asc=user_ratings_asc,
            model=None,
            movie_id_to_details=_movie_id_to_details,
        )

    # STEP 5: prepare_user_context_for_prediction pads to MAX_CONTEXT_LENGTH with 0
    prediction_context_ids = prepare_user_context_for_prediction(context_ids_in_vocab)

    # STEP 6: model input tensor (shape: 1 × MAX_CONTEXT_LENGTH)
    context_tensor = tf.constant([prediction_context_ids], dtype=tf.int32)

    # -----------------------------------------------------------------------
    # STEP 7: RETRIEVAL — GRU encodes history, BruteForce returns top-K ids
    # Note on scores: keras_rs.BruteForceRetrieval with return_scores=False
    # returns only sorted indices. We cannot expose real dot-product scores
    # without changing the layer config and retraining. score=None is honest.
    # -----------------------------------------------------------------------
    try:
        model_output = _model(context_tensor, training=False)
        predicted_ids_tensor = model_output["predictions"]
        predicted_internal_movie_ids = (
            predicted_ids_tensor.numpy()[0]
            if hasattr(predicted_ids_tensor, "numpy")
            else list(predicted_ids_tensor[0])
        )
    except Exception as e:
        logger.error(
            f"Prediction error for user {user.id}: {e}. Falling back to popularity.",
            exc_info=True,
        )
        exclude_ids = user_movie_ids_asc if exclude_watched else []
        return await _get_popularity_fallback(
            db=db,
            exclude_movie_ids=exclude_ids,
            num_recommendations=num_recommendations,
        )

    # -----------------------------------------------------------------------
    # STEPS 8-10: FILTER RATED + VOCAB GUARD + RANK / TOP-K (with optional MMR)
    # -----------------------------------------------------------------------
    watched_ids_set = set(user_movie_ids_asc) if exclude_watched else set()
    valid_candidate_ids: List[int] = []

    for raw_id in predicted_internal_movie_ids:
        internal_id = int(raw_id)
        if internal_id == 0 or internal_id > _movies_count_at_load:
            continue
        if internal_id in watched_ids_set:
            continue
        if internal_id not in valid_candidate_ids:
            valid_candidate_ids.append(internal_id)

    # Optional MMR Re-ranking if enabled
    if settings.ENABLE_MMR_RERANKING and len(valid_candidate_ids) > num_recommendations:
        top_k_movie_ids = mmr_rerank(
            valid_candidate_ids,
            _model,
            k=num_recommendations,
            lambda_param=settings.MMR_LAMBDA,
        )
    else:
        top_k_movie_ids = valid_candidate_ids[:num_recommendations]

    added_ids_set: set = set()
    recommendations: List[Dict[str, Any]] = []

    for internal_id in top_k_movie_ids:
        movie_detail_info = _movie_id_to_details.get(internal_id)
        if movie_detail_info:
            recommendations.append(
                {
                    "movie_id": internal_id,
                    "movie_lens_id": movie_detail_info.get("movie_lens_id"),
                    "title": movie_detail_info.get("title"),
                    "resource_url": movie_detail_info.get("resource_url"),
                    "genres": movie_detail_info.get("genres"),
                    # Honest labelling: this item came from the GRU4Rec model
                    "source": "gru4rec",
                    # score=None: BruteForce returns sorted indices only,
                    # not raw dot-product values. We do not fabricate or normalize.
                    "score": None,
                    "is_personalized": True,
                    "user_rating_count": len(user_movie_ids_asc),
                }
            )
            added_ids_set.add(internal_id)
        else:
            logger.warning(
                f"Internal ID {internal_id} predicted but not in detail cache "
                f"(vocab ceiling={_movies_count_at_load})."
            )

    # -----------------------------------------------------------------------
    # STEP 11: BACKFILL with popularity if model produced fewer than count
    # -----------------------------------------------------------------------
    if len(recommendations) < num_recommendations:
        needed = num_recommendations - len(recommendations)
        exclude_ids = list(watched_ids_set | added_ids_set)
        fallback_recs = await _get_popularity_fallback(
            db, exclude_movie_ids=exclude_ids, num_recommendations=needed
        )
        for item in fallback_recs:
            item["user_rating_count"] = len(user_movie_ids_asc)
        recommendations.extend(fallback_recs)

    # -----------------------------------------------------------------------
    # STEP 12: ATTACH HONEST EXPLANATIONS
    # -----------------------------------------------------------------------
    recommendations = attach_explanations_to_recommendations(
        recommendations=recommendations,
        user_ratings_asc=user_ratings_asc,
        model=_model,
        movie_id_to_details=_movie_id_to_details,
        similarity_threshold=settings.SIMILARITY_EXPLANATION_THRESHOLD,
    )

    return recommendations


# ---------------------------------------------------------------------------
# Debug/audit view: full inference trace (admin only, never exposed to users)
# ---------------------------------------------------------------------------


async def get_inference_trace_for_user(
    db: AsyncSession,
    user: models.User,
    num_recommendations: int = 10,
) -> Dict[str, Any]:
    """
    Returns a structured audit trace of every step in the inference pipeline.
    This is exposed ONLY to admin users via the /recommendations/debug/me endpoint.
    Regular users must never see this data.

    Returns:
        {
          "user_id": int,
          "rating_count": int,
          "sequence_titles": [str],          # ascending-ordered titles from history
          "padded_input_window": [int],       # exactly what was sent to the model
          "oov_ids_skipped": [int],           # IDs filtered before model input
          "raw_retrieved_ids": [int],         # raw sorted output from BruteForce
          "ids_removed_already_rated": [int], # IDs filtered in step 8
          "final_top_k_ids": [int],           # final list passed to response
          "model_available": bool,
          "model_vocab_ceiling": int | None,
          "threshold_used": int,
          "below_threshold": bool,
        }
    """
    user_ratings_desc = await crud.rating.get_ratings_by_user(
        db, user_id=user.id, limit=settings.MAX_CONTEXT_LENGTH * 2
    )
    user_ratings_asc = list(reversed(user_ratings_desc))
    user_movie_ids_asc = [r.movie_id for r in user_ratings_asc]

    # Build sequence_titles from movie cache or DB
    await load_model_and_mappings(db)
    model_available = _model is not None and _movie_id_to_details is not None

    def resolve_title(mid: int) -> str:
        if model_available and mid in _movie_id_to_details:
            return _movie_id_to_details[mid].get("title", f"Movie#{mid}")
        return f"Movie#{mid}"

    sequence_titles = [resolve_title(mid) for mid in user_movie_ids_asc]

    below_threshold = len(user_movie_ids_asc) < settings.MIN_SEQUENCE_LENGTH

    if below_threshold or not model_available or _movies_count_at_load is None:
        return {
            "user_id": user.id,
            "rating_count": len(user_movie_ids_asc),
            "sequence_titles": sequence_titles,
            "padded_input_window": [],
            "oov_ids_skipped": [],
            "raw_retrieved_ids": [],
            "ids_removed_already_rated": [],
            "final_top_k_ids": [],
            "model_available": model_available,
            "model_vocab_ceiling": _movies_count_at_load,
            "threshold_used": settings.MIN_SEQUENCE_LENGTH,
            "below_threshold": below_threshold,
        }

    context_ids = user_movie_ids_asc[-settings.MAX_CONTEXT_LENGTH :]
    oov_ids = [mid for mid in context_ids if mid > _movies_count_at_load]
    context_ids_in_vocab = [mid for mid in context_ids if mid <= _movies_count_at_load]
    padded = prepare_user_context_for_prediction(context_ids_in_vocab)

    raw_retrieved: List[int] = []
    if context_ids_in_vocab:
        try:
            context_tensor = tf.constant([padded], dtype=tf.int32)
            model_output = _model(context_tensor, training=False)
            predicted_ids_tensor = model_output["predictions"]
            raw_ids = (
                predicted_ids_tensor.numpy()[0]
                if hasattr(predicted_ids_tensor, "numpy")
                else list(predicted_ids_tensor[0])
            )
            raw_retrieved = [int(x) for x in raw_ids if int(x) != 0]
        except Exception as e:
            logger.error(f"Trace: model error: {e}", exc_info=True)

    watched_set = set(user_movie_ids_asc)
    removed_rated = [mid for mid in raw_retrieved if mid in watched_set]
    final_ids = []
    added = set()
    for mid in raw_retrieved:
        if mid in watched_set or mid in added or mid > _movies_count_at_load:
            continue
        final_ids.append(mid)
        added.add(mid)
        if len(final_ids) >= num_recommendations:
            break

    return {
        "user_id": user.id,
        "rating_count": len(user_movie_ids_asc),
        "sequence_titles": sequence_titles,
        "padded_input_window": padded,
        "oov_ids_skipped": oov_ids,
        "raw_retrieved_ids": raw_retrieved,
        "ids_removed_already_rated": removed_rated,
        "final_top_k_ids": final_ids,
        "model_available": model_available,
        "model_vocab_ceiling": _movies_count_at_load,
        "threshold_used": settings.MIN_SEQUENCE_LENGTH,
        "below_threshold": False,
    }
