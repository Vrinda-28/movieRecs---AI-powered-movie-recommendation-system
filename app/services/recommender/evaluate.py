import asyncio
import collections
import csv
import json
import logging
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import keras
import numpy as np
import pandas as pd
import tensorflow as tf
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import crud
from app.db.models import Rating
from app.db.session import AsyncSessionLocal
from app.services.recommender.model import SequentialRetrievalModel
from app.services.recommender.preprocessing import (
    MIN_RATING_FILTER,
    MIN_SEQUENCE_LENGTH,
    prepare_user_context_for_prediction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def compute_toy_example_metrics() -> Dict[str, float]:
    """
    Computes the Stage 2 Section 2.1.5 toy example:
    Top 5 = [a, b, c, d, e] (e.g. [1, 2, 3, 4, 5])
    Relevant items = {b, e} (e.g. {2, 5})
    Expected:
      Precision@5 = 2/5 = 0.40
      Recall@5 = 2/2 = 1.00
      Hit Rate@5 = 1.0
      DCG@5 = 1/log2(3) + 1/log2(6) = 0.63092975 + 0.3868528 = 1.01778255
      IDCG@5 = 1/log2(2) + 1/log2(3) = 1.0 + 0.63092975 = 1.63092975
      NDCG@5 = 1.01778255 / 1.63092975 = 0.624050
    """
    ranked_items = ["a", "b", "c", "d", "e"]
    relevant_items = {"b", "e"}
    k = 5

    hits = [1 if item in relevant_items else 0 for item in ranked_items[:k]]
    num_relevant_in_top_k = sum(hits)
    precision = num_relevant_in_top_k / k
    recall = num_relevant_in_top_k / len(relevant_items)
    hit_rate = 1.0 if num_relevant_in_top_k > 0 else 0.0

    dcg = 0.0
    for rank_idx, hit in enumerate(hits):
        if hit:
            dcg += 1.0 / math.log2(rank_idx + 2)

    idcg = 0.0
    for rank_idx in range(min(len(relevant_items), k)):
        idcg += 1.0 / math.log2(rank_idx + 2)

    ndcg = (dcg / idcg) if idcg > 0 else 0.0

    return {
        "precision@5": round(precision, 4),
        "recall@5": round(recall, 4),
        "hit_rate@5": round(hit_rate, 4),
        "ndcg@5": round(ndcg, 4),
    }


def calculate_metrics_for_user(
    ranked_movie_ids: List[int],
    held_out_target: int,
    k_values: List[int] = [5, 10, 20],
) -> Dict[str, float]:
    """
    Computes Precision@K, Recall@K, HitRate@K, NDCG@K for a single user with 1 held-out item.
    """
    metrics = {}
    for k in k_values:
        top_k = ranked_movie_ids[:k]
        hit = 1.0 if held_out_target in top_k else 0.0
        precision = hit / k
        recall = hit  # 1 held-out target: 1/1 if hit else 0/1
        hit_rate = hit

        # Rank of target item (0-indexed)
        if held_out_target in top_k:
            rank = top_k.index(held_out_target)
            ndcg = 1.0 / math.log2(rank + 2)  # Ideal DCG for 1 item at rank 0 is 1.0/log2(2) = 1.0
        else:
            ndcg = 0.0

        metrics[f"precision@{k}"] = precision
        metrics[f"recall@{k}"] = recall
        metrics[f"hit_rate@{k}"] = hit_rate
        metrics[f"ndcg@{k}"] = ndcg

    return metrics


async def evaluate_leave_last_out(
    db: AsyncSession,
    model_path: Optional[str] = None,
    k_values: List[int] = [5, 10, 20],
    output_dir: str = "./evaluation_output",
) -> Dict[str, Any]:
    """
    Executes a chronological leave-last-out evaluation on all users with sufficient ratings.
    Evaluates both GRU4Rec model and a Popularity baseline without data leakage.
    """
    target_model_path = model_path or settings.MODEL_PATH
    logger.info(f"Starting Leave-Last-Out evaluation using model at {target_model_path}...")

    # 1. Fetch all ratings from DB
    raw_ratings: List[Rating] = await crud.rating.get_all_ratings_for_training(db)
    if not raw_ratings:
        logger.error("No ratings in database to evaluate!")
        return {"error": "No ratings found"}

    # Convert to dataframe & filter minimum rating
    df = pd.DataFrame(
        [
            {
                "user_id": r.user_id,
                "movie_id": r.movie_id,
                "rating": r.rating,
                "timestamp": r.timestamp,
            }
            for r in raw_ratings
        ]
    )
    df = df[df["rating"] >= MIN_RATING_FILTER]

    # Group by user & sort chronologically
    user_sequences: Dict[int, List[int]] = collections.defaultdict(list)
    for _, row in df.sort_values(by=["user_id", "timestamp"]).iterrows():
        user_sequences[int(row["user_id"])].append(int(row["movie_id"]))

    # Filter eligible users (at least MIN_SEQUENCE_LENGTH interactions)
    eligible_users = {
        uid: seq for uid, seq in user_sequences.items() if len(seq) >= MIN_SEQUENCE_LENGTH
    }
    logger.info(
        f"Total users: {len(user_sequences)}, Eligible users (>= {MIN_SEQUENCE_LENGTH} ratings): {len(eligible_users)}"
    )

    if not eligible_users:
        logger.error("No eligible users for evaluation.")
        return {"error": "No eligible users"}

    # 2. Build training interactions set for popularity baseline (excluding held-out test items)
    training_movie_counts = collections.Counter()
    test_data: List[Tuple[int, List[int], int]] = []  # (user_id, context_history, held_out_target)

    for uid, seq in eligible_users.items():
        context_history = seq[:-1]
        held_out_target = seq[-1]
        test_data.append((uid, context_history, held_out_target))
        for m in context_history:
            training_movie_counts[m] += 1

    # Sorted list of popular movies from training split
    popular_movies_ranking = [
        m for m, _ in training_movie_counts.most_common()
    ]

    # 3. Load GRU4Rec Model
    model = None
    if os.path.exists(target_model_path):
        try:
            model = keras.models.load_model(
                target_model_path,
                custom_objects={"SequentialRetrievalModel": SequentialRetrievalModel},
            )
            logger.info("GRU4Rec model loaded successfully for evaluation.")
        except Exception as e:
            logger.warning(f"Could not load model at {target_model_path}: {e}")

    # 4. Evaluate each test user
    model_user_metrics: List[Dict[str, float]] = []
    pop_user_metrics: List[Dict[str, float]] = []

    max_k = max(k_values)
    retrieval_limit = max(max_k * 3, 60)

    for uid, context_history, held_out_target in test_data:
        watched_set = set(context_history)

        # Evaluate Popularity Baseline
        # Exclude watched context items, rank remaining by popularity
        pop_candidates = [m for m in popular_movies_ranking if m not in watched_set][:max_k]
        pop_metrics = calculate_metrics_for_user(pop_candidates, held_out_target, k_values)
        pop_user_metrics.append(pop_metrics)

        # Evaluate GRU4Rec Model (if available)
        if model is not None:
            context_ids = prepare_user_context_for_prediction(context_history)
            context_tensor = tf.constant([context_ids], dtype=tf.int32)
            try:
                preds = model(context_tensor, training=False)["predictions"]
                raw_pred_ids = (
                    preds.numpy()[0] if hasattr(preds, "numpy") else list(preds[0])
                )
                model_candidates = []
                for pid in raw_pred_ids:
                    pid_int = int(pid)
                    if pid_int != 0 and pid_int not in watched_set and pid_int not in model_candidates:
                        model_candidates.append(pid_int)
                    if len(model_candidates) >= max_k:
                        break

                m_metrics = calculate_metrics_for_user(model_candidates, held_out_target, k_values)
                model_user_metrics.append(m_metrics)
            except Exception as e:
                logger.error(f"Error predicting for user {uid}: {e}")

    # 5. Aggregate metrics
    def aggregate(metrics_list: List[Dict[str, float]]) -> Dict[str, float]:
        if not metrics_list:
            return {}
        agg = {}
        for key in metrics_list[0].keys():
            agg[key] = float(np.mean([m[key] for m in metrics_list]))
        return agg

    agg_model_metrics = aggregate(model_user_metrics)
    agg_pop_metrics = aggregate(pop_user_metrics)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evaluated_users_count": len(test_data),
        "total_ratings_evaluated": len(df),
        "min_sequence_length": MIN_SEQUENCE_LENGTH,
        "k_values": k_values,
        "toy_example_validation": compute_toy_example_metrics(),
        "gru4rec_model": agg_model_metrics,
        "popularity_baseline": agg_pop_metrics,
    }

    # 6. Save results to JSON and CSV
    os.makedirs(output_dir, exist_ok=True)
    json_path = os.path.join(output_dir, "evaluation_results.json")
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
    logger.info(f"Evaluation JSON saved to {json_path}")

    csv_path = os.path.join(output_dir, "evaluation_results.csv")
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Model", "K", "Precision@K", "Recall@K", "HitRate@K", "NDCG@K"])
        for k in k_values:
            if agg_model_metrics:
                writer.writerow(
                    [
                        "GRU4Rec",
                        k,
                        round(agg_model_metrics.get(f"precision@{k}", 0.0), 4),
                        round(agg_model_metrics.get(f"recall@{k}", 0.0), 4),
                        round(agg_model_metrics.get(f"hit_rate@{k}", 0.0), 4),
                        round(agg_model_metrics.get(f"ndcg@{k}", 0.0), 4),
                    ]
                )
            if agg_pop_metrics:
                writer.writerow(
                    [
                        "Popularity Baseline",
                        k,
                        round(agg_pop_metrics.get(f"precision@{k}", 0.0), 4),
                        round(agg_pop_metrics.get(f"recall@{k}", 0.0), 4),
                        round(agg_pop_metrics.get(f"hit_rate@{k}", 0.0), 4),
                        round(agg_pop_metrics.get(f"ndcg@{k}", 0.0), 4),
                    ]
                )
    logger.info(f"Evaluation CSV saved to {csv_path}")

    return results


async def main():
    async with AsyncSessionLocal() as db:
        results = await evaluate_leave_last_out(db)
        print("\n=== EVALUATION RESULTS ===")
        print(json.dumps(results, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
