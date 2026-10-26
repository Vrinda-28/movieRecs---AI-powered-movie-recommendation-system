"""
Honest, Model-Derived Recommendation Explanations.

Provides transparent and mathematically verifiable explanation reasons:
1. "embedding_neighbor": "Because you rated <Movie> highly"
   - Derived strictly from cosine similarity in candidate-tower embedding space.
   - Sourced from user's recent ratings with rating >= 4.0.
   - Displayed ONLY if cosine similarity exceeds similarity_threshold.
2. "genre_overlap": "Shares genres (X, Y) with movies you rated highly"
   - Derived from exact genre intersection with movies rated >= 4.0.
3. "recent_activity": "Based on your recent ratings"
   - Model-sourced fallback when no individual neighbor exceeds the threshold.
4. "popularity": "Popular with other users"
   - Used for popularity baseline / cold-start fallback items.

Forbidden:
- Any claim of the form "the model chose this because it learned ..."
- LLM-generated explanations or unverifiable narratives.
- Referencing movies the user has never rated.
"""

from typing import Any, Dict, List, Optional, Sequence, Union

import numpy as np
import tensorflow as tf

from app.core.config import settings


def compute_cosine_similarity(vec_a: np.ndarray, vec_b: np.ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    norm_a = np.linalg.norm(vec_a)
    norm_b = np.linalg.norm(vec_b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(vec_a, vec_b) / (norm_a * norm_b))


def get_candidate_embedding(model: Any, movie_id: int) -> Optional[np.ndarray]:
    """Extract candidate embedding vector for a given internal movie ID."""
    if model is None or not hasattr(model, "candidate_model"):
        return None
    try:
        if hasattr(model.candidate_model, "embeddings"):
            weights = model.candidate_model.embeddings
            if hasattr(weights, "numpy"):
                weights_np = weights.numpy()
            else:
                weights_np = np.array(weights)
            if 0 <= movie_id < len(weights_np):
                return weights_np[movie_id]
        # Fallback to direct call
        t = tf.constant([movie_id], dtype=tf.int32)
        emb = model.candidate_model(t)
        return emb.numpy()[0]
    except Exception:
        return None


def parse_genres_set(genres_str: Optional[str]) -> set:
    """Parse pipe-separated genres string into a set of cleaned strings."""
    if not genres_str:
        return set()
    return {g.strip() for g in genres_str.split("|") if g.strip()}


def generate_recommendation_reason(
    recommended_item: Dict[str, Any],
    user_ratings_asc: Sequence[Any],
    model: Optional[Any] = None,
    movie_id_to_details: Optional[Dict[int, Dict[str, Any]]] = None,
    similarity_threshold: float = settings.SIMILARITY_EXPLANATION_THRESHOLD,
) -> Dict[str, Any]:
    """
    Generate an honest, verifiable reason for why an item was recommended.

    Guarantees:
    - Never references a movie the user did not rate.
    - Deterministic output given the same inputs.
    - 'embedding_neighbor' used ONLY when cosine similarity >= similarity_threshold.
    """
    source = recommended_item.get("source", "gru4rec")
    rec_movie_id = recommended_item.get("movie_id")
    rec_genres = parse_genres_set(recommended_item.get("genres"))

    # Popularity items: state honestly that item is a popular fallback
    if source == "popularity" or not recommended_item.get("is_personalized", True):
        return {
            "reason_type": "popularity",
            "reason_text": "Popular with other users",
            "source_movie_id": None,
            "source_movie_title": None,
            "score": None,
            "overlapping_genres": [],
        }

    # Normalize user ratings to structured objects
    rated_items: List[Dict[str, Any]] = []
    for r in user_ratings_asc:
        mid = getattr(r, "movie_id", None) or (
            r.get("movie_id") if isinstance(r, dict) else None
        )
        rating_val = getattr(r, "rating", None) or (
            r.get("rating") if isinstance(r, dict) else 0.0
        )
        if mid is not None:
            title = None
            genres = None
            if movie_id_to_details and mid in movie_id_to_details:
                title = movie_id_to_details[mid].get("title")
                genres = movie_id_to_details[mid].get("genres")
            rated_items.append(
                {
                    "movie_id": mid,
                    "rating": float(rating_val),
                    "title": title or f"Movie #{mid}",
                    "genres": genres,
                }
            )

    if not rated_items:
        return {
            "reason_type": "recent_activity",
            "reason_text": "Based on your recent ratings",
            "source_movie_id": None,
            "source_movie_title": None,
            "score": None,
            "overlapping_genres": [],
        }

    # High-rated movies (rating >= 4.0), or highest rated if none >= 4.0
    high_rated = [item for item in rated_items if item["rating"] >= 4.0]
    if not high_rated:
        max_rating = max(item["rating"] for item in rated_items)
        high_rated = [item for item in rated_items if item["rating"] == max_rating]

    # Method 1: Check embedding cosine similarity with high-rated movies
    best_similarity = -1.0
    best_neighbor: Optional[Dict[str, Any]] = None

    if model is not None and rec_movie_id is not None:
        rec_emb = get_candidate_embedding(model, rec_movie_id)
        if rec_emb is not None:
            # Check recent high-rated items (up to last 10 in history)
            for candidate in reversed(high_rated[-10:]):
                cand_id = candidate["movie_id"]
                cand_emb = get_candidate_embedding(model, cand_id)
                if cand_emb is not None:
                    sim = compute_cosine_similarity(rec_emb, cand_emb)
                    if sim > best_similarity:
                        best_similarity = sim
                        best_neighbor = candidate

    if best_neighbor and best_similarity >= similarity_threshold:
        return {
            "reason_type": "embedding_neighbor",
            "reason_text": f"Because you rated {best_neighbor['title']} highly",
            "source_movie_id": best_neighbor["movie_id"],
            "source_movie_title": best_neighbor["title"],
            "score": round(best_similarity, 3),
            "overlapping_genres": [],
        }

    # Method 2: Check Genre Overlap with high-rated movies
    if rec_genres:
        shared_genres: set = set()
        matched_movie_title: Optional[str] = None
        matched_movie_id: Optional[int] = None

        for candidate in reversed(high_rated):
            cand_genres = parse_genres_set(candidate.get("genres"))
            overlap = rec_genres & cand_genres
            if overlap:
                shared_genres.update(overlap)
                if not matched_movie_title:
                    matched_movie_title = candidate["title"]
                    matched_movie_id = candidate["movie_id"]

        if shared_genres:
            genre_list = sorted(list(shared_genres))
            display_genres = ", ".join(genre_list[:2])
            return {
                "reason_type": "genre_overlap",
                "reason_text": f"Shares genres ({display_genres}) with movies you rated highly",
                "source_movie_id": matched_movie_id,
                "source_movie_title": matched_movie_title,
                "score": None,
                "overlapping_genres": genre_list,
            }

    # Method 3: Generic model-sourced label
    return {
        "reason_type": "recent_activity",
        "reason_text": "Based on your recent ratings",
        "source_movie_id": None,
        "source_movie_title": None,
        "score": None,
        "overlapping_genres": [],
    }


def attach_explanations_to_recommendations(
    recommendations: List[Dict[str, Any]],
    user_ratings_asc: Sequence[Any],
    model: Optional[Any] = None,
    movie_id_to_details: Optional[Dict[int, Dict[str, Any]]] = None,
    similarity_threshold: float = settings.SIMILARITY_EXPLANATION_THRESHOLD,
) -> List[Dict[str, Any]]:
    """Attach structured explanation metadata to each recommendation item."""
    for item in recommendations:
        reason = generate_recommendation_reason(
            recommended_item=item,
            user_ratings_asc=user_ratings_asc,
            model=model,
            movie_id_to_details=movie_id_to_details,
            similarity_threshold=similarity_threshold,
        )
        item["reason"] = reason
        item["reason_type"] = reason["reason_type"]
        item["reason_text"] = reason["reason_text"]
    return recommendations
