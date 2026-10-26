"""
app/services/recommender/evaluate.py — Evaluation Harness for GRU4Rec and Popularity Baseline

Features:
  1. Leak-Free Chronological Leave-Last-Out Evaluation:
     - Splits each eligible user's history chronologically.
     - Holds out the last interaction r_last for evaluation.
     - Trains the model strictly on earlier interactions (r_1 ... r_{n-1}) with zero test leakage.
     - Evaluates whether r_last appears in top-K recommendations.
  2. Optimistic Evaluation Function (evaluate_saved_model_optimistic):
     - Kept for legacy inspection of pre-trained models with explicit leakage warning docstring.
  3. Metrics computed at K in {5, 10, 20}:
     - Precision@K, Recall@K, Hit Rate@K, NDCG@K.
  4. Popularity Baseline:
     - Computed strictly from training split (excluding held-out targets and user's context items).
  5. 95% Bootstrap Confidence Intervals:
     - 1,000 bootstrap resamples on user metrics for Hit Rate@10 and NDCG@10.
  6. Catalogue Coverage & Inference Latency tracking.
  7. Multi-seed execution (default 3 seeds) reporting mean and standard deviation / range.
  8. Artifact persistence to models_store/evaluation/<timestamp>.json and .csv.
"""

import argparse
import asyncio
import collections
import csv
import json
import logging
import math
import os
import random
import time
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
    create_tf_datasets,
    generate_examples_from_user_sequences,
    get_movie_sequence_per_user,
    prepare_user_context_for_prediction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ─── TOY EXAMPLE & METRIC COMPUTATION ──────────────────────────────────────────


def compute_toy_example_metrics() -> Dict[str, float]:
    """
    Computes the Stage 2 Section 2.1.5 worked example:
    Top 5 = [a, b, c, d, e], Relevant = {b, e}
    Expected:
      Precision@5 = 2/5 = 0.40
      Recall@5 = 2/2 = 1.00
      Hit Rate@5 = 1.00
      DCG@5 = 1/log2(3) + 1/log2(6) = 0.63092975 + 0.3868528 = 1.01778255
      IDCG@5 = 1/log2(2) + 1/log2(3) = 1.0 + 0.63092975 = 1.63092975
      NDCG@5 = 1.01778255 / 1.63092975 = 0.624050
    """
    ranked_items = ["a", "b", "c", "d", "e"]
    relevant_items = {"b", "e"}
    k = 5

    hits = [1 if item in relevant_items else 0 for item in ranked_items[:k]]
    num_relevant = sum(hits)
    precision = num_relevant / k
    recall = num_relevant / len(relevant_items)
    hit_rate = 1.0 if num_relevant > 0 else 0.0

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
    Computes Precision@K, Recall@K, HitRate@K, and NDCG@K for 1 held-out target item.
    """
    metrics = {}
    for k in k_values:
        top_k = ranked_movie_ids[:k]
        hit = 1.0 if held_out_target in top_k else 0.0
        precision = hit / k
        recall = hit  # 1 target: hit / 1
        hit_rate = hit

        if held_out_target in top_k:
            rank = top_k.index(held_out_target)
            ndcg = 1.0 / math.log2(rank + 2)
        else:
            ndcg = 0.0

        metrics[f"precision@{k}"] = precision
        metrics[f"recall@{k}"] = recall
        metrics[f"hit_rate@{k}"] = hit_rate
        metrics[f"ndcg@{k}"] = ndcg

    return metrics


def compute_bootstrap_ci(
    values: List[float], n_bootstraps: int = 1000, ci: float = 0.95, seed: int = 42
) -> Tuple[float, float, float]:
    """
    Computes bootstrap confidence interval (mean, lower_bound, upper_bound).
    """
    if not values:
        return 0.0, 0.0, 0.0
    rng = np.random.default_rng(seed)
    n = len(values)
    arr = np.array(values)
    boot_means = np.empty(n_bootstraps)
    for i in range(n_bootstraps):
        resample = rng.choice(arr, size=n, replace=True)
        boot_means[i] = np.mean(resample)

    alpha = (1.0 - ci) / 2.0
    lower = float(np.percentile(boot_means, alpha * 100))
    upper = float(np.percentile(boot_means, (1.0 - alpha) * 100))
    mean = float(np.mean(arr))
    return round(mean, 4), round(lower, 4), round(upper, 4)


# ─── DATA PREPARATION & SPLITTING ──────────────────────────────────────────────


def build_leave_last_out_splits(
    ratings_df: pd.DataFrame,
) -> Tuple[Dict[int, List[Dict[str, Any]]], List[Tuple[int, List[int], int]], int]:
    """
    Performs chronological leave-last-out split:
      - For each user with >= MIN_SEQUENCE_LENGTH ratings, holds out the LAST interaction.
      - Returns:
          1. train_sequences: Dict[user_id, list of interactions strictly excluding the last one]
          2. test_instances: List of (user_id, context_movie_ids, held_out_target_id)
          3. max_movie_id: Maximum movie ID observed in dataset
    """
    user_sequences = get_movie_sequence_per_user(ratings_df)
    train_sequences: Dict[int, List[Dict[str, Any]]] = {}
    test_instances: List[Tuple[int, List[int], int]] = []
    max_movie_id = int(ratings_df["movie_id"].max()) if not ratings_df.empty else 0

    for uid, seq in user_sequences.items():
        if len(seq) >= MIN_SEQUENCE_LENGTH:
            # Hold out the very last interaction
            train_seq = seq[:-1]
            held_out = seq[-1]
            train_sequences[uid] = train_seq
            context_ids = [m["movie_id"] for m in train_seq]
            target_id = held_out["movie_id"]
            test_instances.append((uid, context_ids, target_id))
        else:
            # Users below threshold are part of general background if usable
            train_sequences[uid] = seq

    return train_sequences, test_instances, max_movie_id


# ─── LEAK-FREE EVALUATION PIPELINE ─────────────────────────────────────────────


async def evaluate_single_run_leakfree(
    train_sequences: Dict[int, List[Dict[str, Any]]],
    test_instances: List[Tuple[int, List[int], int]],
    max_movie_id: int,
    total_catalogue_movies: int,
    k_values: List[int] = [5, 10, 20],
    epochs: int = 10,
    batch_size: int = 256,
    learning_rate: float = 0.005,
    embedding_dim: int = 32,
    gru_units: int = 32,
    mask_zero: bool = True,
    padding_mode: str = "right",
    seed: int = 42,
) -> Dict[str, Any]:
    """
    Runs one full leak-free evaluation cycle:
      1. Generates training examples strictly from train_sequences (zero leakage).
      2. Computes training-set popularity baseline.
      3. Trains a fresh model with the given seed.
      4. Evaluates both models on test_instances.
      5. Calculates latency, coverage, and bootstrap CIs.
    """
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)

    # 1. Popularity Baseline Ranking from training split only
    train_movie_counter = collections.Counter()
    for seq in train_sequences.values():
        for item in seq:
            train_movie_counter[item["movie_id"]] += 1
    popular_movies_ranked = [m for m, _ in train_movie_counter.most_common()]

    # 2. Build training dataset for GRU4Rec
    train_examples = generate_examples_from_user_sequences(
        train_sequences,
        max_context_length=settings.MAX_CONTEXT_LENGTH,
        padding_mode=padding_mode,
    )
    if not train_examples:
        return {"error": "No training examples from train_sequences"}

    train_ds = create_tf_datasets(
        train_examples, batch_size=batch_size, is_training=True
    )

    # 3. Train model
    model = SequentialRetrievalModel(
        movies_count=max_movie_id,
        embedding_dimension=embedding_dim,
        gru_units=gru_units,
        mask_zero=mask_zero,
    )
    model.compile(optimizer=keras.optimizers.AdamW(learning_rate=learning_rate))
    model(tf.zeros((1, settings.MAX_CONTEXT_LENGTH), dtype=tf.int32))

    t0_train = time.time()
    history = model.fit(train_ds, epochs=epochs, verbose=0)
    train_duration = time.time() - t0_train

    # 4. Evaluation Loop
    max_k = max(k_values)
    model_user_metrics = []
    pop_user_metrics = []

    model_recommended_items: Set[int] = set()
    pop_recommended_items: Set[int] = set()

    inference_latencies_ms = []

    # GRU4Rec Batched Prediction
    all_padded = [
        prepare_user_context_for_prediction(
            ctx,
            max_context_length=settings.MAX_CONTEXT_LENGTH,
            padding_mode=padding_mode,
        )
        for _, ctx, _ in test_instances
    ]
    t0_inf = time.perf_counter()
    all_preds_tensor = model(tf.constant(all_padded, dtype=tf.int32), training=False)[
        "predictions"
    ]
    raw_preds_all = (
        all_preds_tensor.numpy()
        if hasattr(all_preds_tensor, "numpy")
        else np.array(all_preds_tensor)
    )
    inf_duration_ms = (time.perf_counter() - t0_inf) * 1000.0
    avg_user_latency_ms = inf_duration_ms / max(len(test_instances), 1)

    for idx, (uid, context_ids, target_id) in enumerate(test_instances):
        watched_set = set(context_ids)

        # Popularity prediction
        pop_candidates = [m for m in popular_movies_ranked if m not in watched_set][
            :max_k
        ]
        pop_metrics = calculate_metrics_for_user(pop_candidates, target_id, k_values)
        pop_user_metrics.append(pop_metrics)
        for item in pop_candidates:
            pop_recommended_items.add(item)

        # GRU4Rec prediction from batched results
        raw_pred_ids = raw_preds_all[idx]
        model_candidates = []
        for pid in raw_pred_ids:
            pid_int = int(pid)
            if (
                pid_int != 0
                and pid_int not in watched_set
                and pid_int not in model_candidates
            ):
                model_candidates.append(pid_int)
            if len(model_candidates) >= max_k:
                break

        m_metrics = calculate_metrics_for_user(model_candidates, target_id, k_values)
        model_user_metrics.append(m_metrics)
        for item in model_candidates:
            model_recommended_items.add(item)

    inference_latencies_ms.append(avg_user_latency_ms)

    # 5. Metric Aggregation
    def summarize_metrics(metrics_list: List[Dict[str, float]]) -> Dict[str, float]:
        summary = {}
        for k in metrics_list[0].keys():
            summary[k] = round(float(np.mean([m[k] for m in metrics_list])), 4)
        return summary

    agg_model = summarize_metrics(model_user_metrics)
    agg_pop = summarize_metrics(pop_user_metrics)

    # 6. Bootstrap CIs for Hit Rate@10 and NDCG@10
    model_hit10_ci = compute_bootstrap_ci(
        [m["hit_rate@10"] for m in model_user_metrics], seed=seed
    )
    model_ndcg10_ci = compute_bootstrap_ci(
        [m["ndcg@10"] for m in model_user_metrics], seed=seed
    )
    pop_hit10_ci = compute_bootstrap_ci(
        [m["hit_rate@10"] for m in pop_user_metrics], seed=seed
    )
    pop_ndcg10_ci = compute_bootstrap_ci(
        [m["ndcg@10"] for m in pop_user_metrics], seed=seed
    )

    # Catalogue coverage
    cat_size = max(total_catalogue_movies, max_movie_id, 1)
    model_coverage = round(len(model_recommended_items) / cat_size, 4)
    pop_coverage = round(len(pop_recommended_items) / cat_size, 4)

    avg_latency = round(float(np.mean(inference_latencies_ms)), 2)

    return {
        "seed": seed,
        "train_duration_seconds": round(train_duration, 2),
        "avg_inference_latency_ms": avg_latency,
        "catalogue_size": cat_size,
        "gru4rec": {
            "metrics": agg_model,
            "catalogue_coverage": model_coverage,
            "distinct_items_recommended": len(model_recommended_items),
            "hit_rate_at_10_ci95": {
                "mean": model_hit10_ci[0],
                "lower": model_hit10_ci[1],
                "upper": model_hit10_ci[2],
            },
            "ndcg_at_10_ci95": {
                "mean": model_ndcg10_ci[0],
                "lower": model_ndcg10_ci[1],
                "upper": model_ndcg10_ci[2],
            },
        },
        "popularity": {
            "metrics": agg_pop,
            "catalogue_coverage": pop_coverage,
            "distinct_items_recommended": len(pop_recommended_items),
            "hit_rate_at_10_ci95": {
                "mean": pop_hit10_ci[0],
                "lower": pop_hit10_ci[1],
                "upper": pop_hit10_ci[2],
            },
            "ndcg_at_10_ci95": {
                "mean": pop_ndcg10_ci[0],
                "lower": pop_ndcg10_ci[1],
                "upper": pop_ndcg10_ci[2],
            },
        },
    }


async def evaluate_leave_last_out_leakfree(
    db: AsyncSession,
    k_values: List[int] = [5, 10, 20],
    seeds: List[int] = [42, 43, 44],
    epochs: int = 10,
    batch_size: int = 256,
    learning_rate: float = 0.005,
    embedding_dim: int = 32,
    gru_units: int = 32,
    mask_zero: bool = True,
    padding_mode: str = "right",
    output_dir: str = "./models_store/evaluation",
) -> Dict[str, Any]:
    """
    Executes a multi-seed, leak-free leave-last-out evaluation on the current database.
    """
    logger.info("Starting Multi-Seed Leak-Free Evaluation Pipeline...")
    raw_ratings = await crud.rating.get_all_ratings_for_training(db)
    if not raw_ratings:
        logger.error("No ratings in DB for evaluation.")
        return {"error": "No ratings in database"}

    ratings_df = pd.DataFrame(
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
    ratings_df = ratings_df[ratings_df["rating"] >= MIN_RATING_FILTER]

    train_sequences, test_instances, max_movie_id = build_leave_last_out_splits(
        ratings_df
    )
    total_catalogue_movies = (
        await crud.movie.get_max_internal_movie_id(db) or max_movie_id
    )

    logger.info(
        f"Evaluation Dataset: {len(test_instances)} test users (leave-last-out), "
        f"{len(train_sequences)} total user histories, Max movie ID: {max_movie_id}"
    )

    seed_results = []
    for s in seeds:
        logger.info(f"--- Running evaluation for seed={s} ---")
        run_res = await evaluate_single_run_leakfree(
            train_sequences=train_sequences,
            test_instances=test_instances,
            max_movie_id=max_movie_id,
            total_catalogue_movies=total_catalogue_movies,
            k_values=k_values,
            epochs=epochs,
            batch_size=batch_size,
            learning_rate=learning_rate,
            embedding_dim=embedding_dim,
            gru_units=gru_units,
            mask_zero=mask_zero,
            padding_mode=padding_mode,
            seed=s,
        )
        seed_results.append(run_res)

    # Average metrics across seeds
    def average_seed_metrics(model_key: str) -> Dict[str, Any]:
        all_metrics_keys = list(seed_results[0][model_key]["metrics"].keys())
        mean_metrics = {}
        for m_key in all_metrics_keys:
            vals = [res[model_key]["metrics"][m_key] for res in seed_results]
            mean_metrics[m_key] = {
                "mean": round(float(np.mean(vals)), 4),
                "min": round(float(np.min(vals)), 4),
                "max": round(float(np.max(vals)), 4),
                "std": round(float(np.std(vals)), 4),
            }

        cov_vals = [res[model_key]["catalogue_coverage"] for res in seed_results]
        return {
            "metrics": mean_metrics,
            "mean_catalogue_coverage": round(float(np.mean(cov_vals)), 4),
            "hit_rate_at_10_ci95": seed_results[0][model_key]["hit_rate_at_10_ci95"],
            "ndcg_at_10_ci95": seed_results[0][model_key]["ndcg_at_10_ci95"],
        }

    overall_results = {
        "evaluation_type": "leak_free_chronological_leave_last_out",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "evaluated_users_count": len(test_instances),
        "total_ratings_evaluated": len(ratings_df),
        "catalogue_size": total_catalogue_movies,
        "seeds_evaluated": seeds,
        "k_values": k_values,
        "hyperparameters": {
            "epochs": epochs,
            "batch_size": batch_size,
            "learning_rate": learning_rate,
            "embedding_dim": embedding_dim,
            "gru_units": gru_units,
            "mask_zero": mask_zero,
            "padding_mode": padding_mode,
        },
        "toy_example_validation": compute_toy_example_metrics(),
        "gru4rec_summary": average_seed_metrics("gru4rec"),
        "popularity_summary": average_seed_metrics("popularity"),
        "individual_seed_runs": seed_results,
    }

    # Save to disk
    os.makedirs(output_dir, exist_ok=True)
    ts_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    json_path = os.path.join(output_dir, f"evaluation_{ts_str}.json")
    latest_json_path = os.path.join(output_dir, "evaluation_latest.json")
    with open(json_path, "w") as f:
        json.dump(overall_results, f, indent=2)
    with open(latest_json_path, "w") as f:
        json.dump(overall_results, f, indent=2)

    csv_path = os.path.join(output_dir, f"evaluation_{ts_str}.csv")
    latest_csv_path = os.path.join(output_dir, "evaluation_latest.csv")
    for cp in (csv_path, latest_csv_path):
        with open(cp, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    "Model",
                    "K",
                    "Precision@K (mean)",
                    "Recall@K (mean)",
                    "HitRate@K (mean)",
                    "NDCG@K (mean)",
                ]
            )
            for k in k_values:
                g_m = overall_results["gru4rec_summary"]["metrics"]
                p_m = overall_results["popularity_summary"]["metrics"]
                writer.writerow(
                    [
                        "GRU4Rec",
                        k,
                        g_m[f"precision@{k}"]["mean"],
                        g_m[f"recall@{k}"]["mean"],
                        g_m[f"hit_rate@{k}"]["mean"],
                        g_m[f"ndcg@{k}"]["mean"],
                    ]
                )
                writer.writerow(
                    [
                        "Popularity Baseline",
                        k,
                        p_m[f"precision@{k}"]["mean"],
                        p_m[f"recall@{k}"]["mean"],
                        p_m[f"hit_rate@{k}"]["mean"],
                        p_m[f"ndcg@{k}"]["mean"],
                    ]
                )

    logger.info(f"Evaluation report saved to {json_path} and {csv_path}")
    return overall_results


# ─── OPTIMISTIC EVALUATION FUNCTION (LEGACY INSPECTION) ────────────────────────


async def evaluate_saved_model_optimistic(
    db: AsyncSession,
    model_path: Optional[str] = None,
    k_values: List[int] = [5, 10, 20],
    output_dir: str = "./models_store/evaluation",
) -> Dict[str, Any]:
    """
    WARNING: Optimistic Evaluation with Data Leakage!

    This function tests an ALREADY-SAVED model checkpoint against leave-last-out items.
    If the saved model was trained on the entire dataset without explicitly holding out
    each user's last interaction, the model has ALREADY SEEN the test targets during training.

    This function is maintained strictly for inspecting existing saved checkpoints and comparing
    leakage bias vs genuine leak-free performance. Use evaluate_leave_last_out_leakfree for
    honest, publication-grade benchmarks.
    """
    target_model_path = model_path or settings.MODEL_PATH
    logger.warning(
        f"Running OPTIMISTIC evaluation on {target_model_path}. "
        "Notice: Results may reflect data leakage if model saw test targets during training."
    )

    raw_ratings = await crud.rating.get_all_ratings_for_training(db)
    if not raw_ratings:
        return {"error": "No ratings found"}

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

    train_sequences, test_instances, max_movie_id = build_leave_last_out_splits(df)

    # Load model
    if not os.path.exists(target_model_path):
        return {"error": f"Model not found at {target_model_path}"}

    model = keras.models.load_model(
        target_model_path,
        custom_objects={"SequentialRetrievalModel": SequentialRetrievalModel},
    )

    max_k = max(k_values)
    model_user_metrics = []
    for uid, context_ids, target_id in test_instances:
        watched_set = set(context_ids)
        padded_input = prepare_user_context_for_prediction(
            context_ids, max_context_length=settings.MAX_CONTEXT_LENGTH
        )
        context_tensor = tf.constant([padded_input], dtype=tf.int32)
        preds = model(context_tensor, training=False)["predictions"]
        raw_pred_ids = preds.numpy()[0] if hasattr(preds, "numpy") else list(preds[0])

        model_candidates = []
        for pid in raw_pred_ids:
            pid_int = int(pid)
            if (
                pid_int != 0
                and pid_int not in watched_set
                and pid_int not in model_candidates
            ):
                model_candidates.append(pid_int)
            if len(model_candidates) >= max_k:
                break

        model_user_metrics.append(
            calculate_metrics_for_user(model_candidates, target_id, k_values)
        )

    def summarize(m_list):
        return {
            k: round(float(np.mean([m[k] for m in m_list])), 4)
            for k in m_list[0].keys()
        }

    results = {
        "evaluation_type": "optimistic_saved_model_with_potential_leakage",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model_path": target_model_path,
        "evaluated_users_count": len(test_instances),
        "gru4rec_metrics": summarize(model_user_metrics) if model_user_metrics else {},
    }
    return results


# ─── CLI DISPATCHER ────────────────────────────────────────────────────────────


def parse_args():
    parser = argparse.ArgumentParser(description="Evaluate Recommendation Models")
    parser.add_argument(
        "--leak-free",
        action="store_true",
        default=True,
        help="Run leak-free evaluation (default: True)",
    )
    parser.add_argument(
        "--optimistic",
        action="store_true",
        help="Run optimistic evaluation on saved model checkpoint",
    )
    parser.add_argument(
        "--k",
        nargs="+",
        type=int,
        default=[5, 10, 20],
        help="K values (default: 5 10 20)",
    )
    parser.add_argument(
        "--seeds", type=int, default=3, help="Number of random seeds (default: 3)"
    )
    parser.add_argument(
        "--epochs", type=int, default=10, help="Epochs for leak-free training"
    )
    parser.add_argument(
        "--batch-size", type=int, default=256, help="Batch size for leak-free training"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./models_store/evaluation",
        help="Output directory",
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    seed_list = [42 + i for i in range(args.seeds)]

    async with AsyncSessionLocal() as db:
        if args.optimistic:
            res = await evaluate_saved_model_optimistic(
                db, k_values=args.k, output_dir=args.output_dir
            )
            print("\n" + "=" * 60)
            print("  OPTIMISTIC EVALUATION RESULTS")
            print("=" * 60)
            print(json.dumps(res, indent=2))
        else:
            res = await evaluate_leave_last_out_leakfree(
                db,
                k_values=args.k,
                seeds=seed_list,
                epochs=args.epochs,
                batch_size=args.batch_size,
                output_dir=args.output_dir,
            )
            print("\n" + "=" * 60)
            print("  LEAK-FREE EVALUATION RESULTS")
            print("=" * 60)
            print(json.dumps(res, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
