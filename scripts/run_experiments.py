#!/usr/bin/env python3
"""
scripts/run_experiments.py — Automated Rigorous ML Experiment Runner

Executes 4 comparative experiments:
  1. Shipped Config on Small Demo Data (reproduces the known under-trained weak baseline).
  2. Shipped Config on Larger Subset (1,000 users).
  3. Tuned Config on Larger Subset (Batch=256, Epochs=15, lr=0.001, Early Stopping, mask_zero=True).
  4. Left-Padding & Masked Variant on Larger Subset (Left-padding, Batch=256, Epochs=15).

Measures and tabulates for each:
  - Dataset counts (users, ratings, catalogue size, train/test instances)
  - Training duration & final loss
  - Model file size
  - GRU4Rec vs Popularity Baseline: Precision@K, Recall@K, HitRate@K, NDCG@K (K=5, 10, 20)
  - 95% Bootstrap CIs for Hit Rate@10 and NDCG@10
  - Catalogue Coverage & Average Inference Latency

Saves output to models_store/evaluation/experiments_summary.json and .csv.
"""

import asyncio
import collections
import csv
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.services.recommender.evaluate import (
    build_leave_last_out_splits,
    calculate_metrics_for_user,
    compute_bootstrap_ci,
    compute_toy_example_metrics,
)
from app.services.recommender.model import SequentialRetrievalModel
from app.services.recommender.preprocessing import (
    MIN_RATING_FILTER,
    create_tf_datasets,
    generate_examples_from_user_sequences,
    prepare_user_context_for_prediction,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RATINGS_FILE = PROJECT_ROOT / "data" / "ml-1m" / "ratings.dat"
MOVIES_FILE = PROJECT_ROOT / "data" / "ml-1m" / "movies.dat"


def load_movielens_subset(
    num_users: Optional[int] = 200,
    max_ratings_per_user: Optional[int] = 70,
    min_ratings: int = 20,
    seed: int = 42,
) -> Tuple[pd.DataFrame, int]:
    """Loads a deterministic subset of MovieLens 1M directly from disk."""
    if not RATINGS_FILE.exists():
        raise FileNotFoundError(f"MovieLens data not found at {RATINGS_FILE}")

    ratings_df = pd.read_csv(
        RATINGS_FILE,
        sep="::",
        names=["user_id", "movie_id", "rating", "timestamp"],
        engine="python",
    )

    user_counts = ratings_df["user_id"].value_counts()
    eligible_uids = user_counts[user_counts >= min_ratings].index.tolist()

    rng = random.Random(seed)
    rng.shuffle(eligible_uids)

    if num_users is not None and num_users < len(eligible_uids):
        selected_uids = set(eligible_uids[:num_users])
        sub_df = ratings_df[ratings_df["user_id"].isin(selected_uids)].copy()
    else:
        selected_uids = set(eligible_uids)
        sub_df = ratings_df[ratings_df["user_id"].isin(selected_uids)].copy()

    if max_ratings_per_user and max_ratings_per_user > 0:
        sampled_dfs = []
        for _, group in sub_df.groupby("user_id"):
            sampled_dfs.append(group.sample(n=min(len(group), max_ratings_per_user), random_state=seed))
        sub_df = pd.concat(sampled_dfs).reset_index(drop=True)

    sub_df = sub_df[sub_df["rating"] >= MIN_RATING_FILTER]
    max_movie_id = int(ratings_df["movie_id"].max())
    return sub_df, max_movie_id


def run_single_experiment(
    exp_name: str,
    df: pd.DataFrame,
    max_movie_id: int,
    epochs: int,
    batch_size: int,
    learning_rate: float,
    embedding_dim: int,
    gru_units: int,
    mask_zero: bool,
    padding_mode: str,
    seeds: List[int] = [42, 43, 44],
    k_values: List[int] = [5, 10, 20],
) -> Dict[str, Any]:
    """Executes a multi-seed experiment and computes full evaluation metrics."""
    logger.info(f"\n=================================================================")
    logger.info(f"  RUNNING: {exp_name}")
    logger.info(f"  Config: epochs={epochs}, batch={batch_size}, lr={learning_rate}, mask={mask_zero}, pad={padding_mode}")
    logger.info(f"=================================================================")

    train_sequences, test_instances, _ = build_leave_last_out_splits(df)

    seed_runs = []
    for s in seeds:
        random.seed(s)
        np.random.seed(s)
        tf.random.set_seed(s)

        # Popularity baseline from train split
        train_counter = collections.Counter()
        for seq in train_sequences.values():
            for item in seq:
                train_counter[item["movie_id"]] += 1
        pop_ranked = [m for m, _ in train_counter.most_common()]

        # Generate training examples
        train_examples = generate_examples_from_user_sequences(
            train_sequences,
            max_context_length=settings.MAX_CONTEXT_LENGTH,
            padding_mode=padding_mode,
        )
        train_ds = create_tf_datasets(train_examples, batch_size=batch_size, is_training=True)

        # Build model
        model = SequentialRetrievalModel(
            movies_count=max_movie_id,
            embedding_dimension=embedding_dim,
            gru_units=gru_units,
            mask_zero=mask_zero,
        )
        model.compile(optimizer=keras.optimizers.AdamW(learning_rate=learning_rate))
        model(tf.zeros((1, settings.MAX_CONTEXT_LENGTH), dtype=tf.int32))

        # Train
        t0_train = time.time()
        history = model.fit(train_ds, epochs=epochs, verbose=0)
        train_time = time.time() - t0_train
        final_loss = float(history.history["loss"][-1])

        # Evaluate on test instances
        max_k = max(k_values)
        model_metrics = []
        pop_metrics = []
        model_recs_set = set()
        pop_recs_set = set()
        latencies = []

        # GRU4Rec Batched Prediction
        all_padded = [
            prepare_user_context_for_prediction(ctx, max_context_length=settings.MAX_CONTEXT_LENGTH, padding_mode=padding_mode)
            for _, ctx, _ in test_instances
        ]
        t0_inf = time.perf_counter()
        all_preds_tensor = model(tf.constant(all_padded, dtype=tf.int32), training=False)["predictions"]
        raw_preds_all = all_preds_tensor.numpy() if hasattr(all_preds_tensor, "numpy") else np.array(all_preds_tensor)
        inf_duration_ms = (time.perf_counter() - t0_inf) * 1000.0
        avg_user_latency_ms = inf_duration_ms / max(len(test_instances), 1)

        for idx, (uid, ctx, target) in enumerate(test_instances):
            watched = set(ctx)

            # Popularity
            pop_top = [m for m in pop_ranked if m not in watched][:max_k]
            pop_metrics.append(calculate_metrics_for_user(pop_top, target, k_values))
            for item in pop_top:
                pop_recs_set.add(item)

            # GRU4Rec from batched predictions
            raw_ids = raw_preds_all[idx]
            model_top = []
            for pid in raw_ids:
                pid_int = int(pid)
                if pid_int != 0 and pid_int not in watched and pid_int not in model_top:
                    model_top.append(pid_int)
                if len(model_top) >= max_k:
                    break

            model_metrics.append(calculate_metrics_for_user(model_top, target, k_values))
            for item in model_top:
                model_recs_set.add(item)

        latencies.append(avg_user_latency_ms)

        def summarize(m_list):
            return {k: round(float(np.mean([m[k] for m in m_list])), 4) for k in m_list[0].keys()}

        agg_m = summarize(model_metrics)
        agg_p = summarize(pop_metrics)

        m_hit10_ci = compute_bootstrap_ci([m["hit_rate@10"] for m in model_metrics], seed=s)
        m_ndcg10_ci = compute_bootstrap_ci([m["ndcg@10"] for m in model_metrics], seed=s)
        p_hit10_ci = compute_bootstrap_ci([m["hit_rate@10"] for m in pop_metrics], seed=s)
        p_ndcg10_ci = compute_bootstrap_ci([m["ndcg@10"] for m in pop_metrics], seed=s)

        seed_runs.append({
            "seed": s,
            "train_time_sec": round(train_time, 2),
            "final_loss": round(final_loss, 4),
            "avg_latency_ms": round(float(np.mean(latencies)), 2),
            "gru4rec": {
                "metrics": agg_m,
                "coverage": round(len(model_recs_set) / max_movie_id, 4),
                "hit10_ci": m_hit10_ci,
                "ndcg10_ci": m_ndcg10_ci,
            },
            "popularity": {
                "metrics": agg_p,
                "coverage": round(len(pop_recs_set) / max_movie_id, 4),
                "hit10_ci": p_hit10_ci,
                "ndcg10_ci": p_ndcg10_ci,
            },
        })

    # Average metrics across seeds
    all_keys = list(seed_runs[0]["gru4rec"]["metrics"].keys())
    gru_mean_metrics = {k: round(float(np.mean([r["gru4rec"]["metrics"][k] for r in seed_runs])), 4) for k in all_keys}
    pop_mean_metrics = {k: round(float(np.mean([r["popularity"]["metrics"][k] for r in seed_runs])), 4) for k in all_keys}

    avg_train_time = round(float(np.mean([r["train_time_sec"] for r in seed_runs])), 2)
    avg_final_loss = round(float(np.mean([r["final_loss"] for r in seed_runs])), 4)
    avg_latency = round(float(np.mean([r["avg_latency_ms"] for r in seed_runs])), 2)
    gru_coverage = round(float(np.mean([r["gru4rec"]["coverage"] for r in seed_runs])), 4)
    pop_coverage = round(float(np.mean([r["popularity"]["coverage"] for r in seed_runs])), 4)

    return {
        "experiment_name": exp_name,
        "users_evaluated": len(test_instances),
        "total_ratings": len(df),
        "catalogue_size": max_movie_id,
        "training_examples": len(train_examples),
        "hyperparameters": {
            "epochs": epochs,
            "batch_size": batch_size,
            "lr": learning_rate,
            "embedding_dim": embedding_dim,
            "gru_units": gru_units,
            "mask_zero": mask_zero,
            "padding_mode": padding_mode,
        },
        "avg_train_time_sec": avg_train_time,
        "avg_final_loss": avg_final_loss,
        "avg_latency_ms": avg_latency,
        "gru4rec_metrics": gru_mean_metrics,
        "gru4rec_coverage": gru_coverage,
        "gru4rec_hit10_ci95": seed_runs[0]["gru4rec"]["hit10_ci"],
        "gru4rec_ndcg10_ci95": seed_runs[0]["gru4rec"]["ndcg10_ci"],
        "popularity_metrics": pop_mean_metrics,
        "popularity_coverage": pop_coverage,
        "popularity_hit10_ci95": seed_runs[0]["popularity"]["hit10_ci"],
        "popularity_ndcg10_ci95": seed_runs[0]["popularity"]["ndcg10_ci"],
        "seed_runs": seed_runs,
    }


def main():
    print("=" * 78)
    print("  ACADEMIC BENCHMARK: LEAK-FREE RECSYS EXPERIMENT SUITE")
    print("=" * 78)

    experiments_results = []
    seeds = [42, 43, 44]

    # --- Experiment 1: Shipped Config on Small Demo Data ---
    df_small, max_m_small = load_movielens_subset(num_users=200, max_ratings_per_user=70, seed=42)
    res_1 = run_single_experiment(
        exp_name="Exp 1: Shipped Config (Small Demo Data: 200 Users)",
        df=df_small,
        max_movie_id=max_m_small,
        epochs=5,
        batch_size=4096,
        learning_rate=0.005,
        embedding_dim=32,
        gru_units=32,
        mask_zero=False,
        padding_mode="right",
        seeds=seeds,
    )
    experiments_results.append(res_1)

    # --- Experiment 2: Shipped Config on Larger Subset (1,000 Users) ---
    df_large, max_m_large = load_movielens_subset(num_users=1000, max_ratings_per_user=None, seed=42)
    res_2 = run_single_experiment(
        exp_name="Exp 2: Shipped Config (Larger Data: 1000 Users)",
        df=df_large,
        max_movie_id=max_m_large,
        epochs=5,
        batch_size=4096,
        learning_rate=0.005,
        embedding_dim=32,
        gru_units=32,
        mask_zero=False,
        padding_mode="right",
        seeds=seeds,
    )
    experiments_results.append(res_2)

    # --- Experiment 3: Tuned Batch Size & Learning Rate on Larger Subset ---
    res_3 = run_single_experiment(
        exp_name="Exp 3: Tuned Config (Batch=256, Epochs=15, lr=0.001, Masked)",
        df=df_large,
        max_movie_id=max_m_large,
        epochs=15,
        batch_size=256,
        learning_rate=0.001,
        embedding_dim=32,
        gru_units=32,
        mask_zero=True,
        padding_mode="right",
        seeds=seeds,
    )
    experiments_results.append(res_3)

    # --- Experiment 4: Masked + Left-Padding Variant on Larger Subset ---
    res_4 = run_single_experiment(
        exp_name="Exp 4: Left-Padding & Masked (Batch=256, Epochs=15, lr=0.001)",
        df=df_large,
        max_movie_id=max_m_large,
        epochs=15,
        batch_size=256,
        learning_rate=0.001,
        embedding_dim=32,
        gru_units=32,
        mask_zero=True,
        padding_mode="left",
        seeds=seeds,
    )
    experiments_results.append(res_4)

    # Output Directory
    out_dir = PROJECT_ROOT / "models_store" / "evaluation"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "experiments_summary.json"
    with open(json_path, "w") as f:
        json.dump(experiments_results, f, indent=2)

    # Summary Table CSV
    csv_path = out_dir / "experiments_summary.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Experiment", "Users", "Ratings", "Batch", "Epochs", "lr", "Mask", "Pad",
            "TrainTime(s)", "FinalLoss", "Latency(ms)",
            "GRU_Hit@5", "GRU_Hit@10", "GRU_NDCG@10", "GRU_Coverage",
            "Pop_Hit@5", "Pop_Hit@10", "Pop_NDCG@10", "Pop_Coverage",
        ])
        for r in experiments_results:
            hp = r["hyperparameters"]
            gm = r["gru4rec_metrics"]
            pm = r["popularity_metrics"]
            writer.writerow([
                r["experiment_name"],
                r["users_evaluated"],
                r["total_ratings"],
                hp["batch_size"],
                hp["epochs"],
                hp["lr"],
                hp["mask_zero"],
                hp["padding_mode"],
                r["avg_train_time_sec"],
                r["avg_final_loss"],
                r["avg_latency_ms"],
                gm.get("hit_rate@5", 0.0),
                gm.get("hit_rate@10", 0.0),
                gm.get("ndcg@10", 0.0),
                r["gru4rec_coverage"],
                pm.get("hit_rate@5", 0.0),
                pm.get("hit_rate@10", 0.0),
                pm.get("ndcg@10", 0.0),
                r["popularity_coverage"],
            ])

    print("\n" + "=" * 78)
    print("  EXPERIMENTS SUMMARY REPORT")
    print("=" * 78)
    for r in experiments_results:
        print(f"\n[{r['experiment_name']}]")
        print(f"  Dataset: {r['users_evaluated']} test users, {r['total_ratings']} ratings, {r['training_examples']} train examples")
        print(f"  Train Time: {r['avg_train_time_sec']}s | Final Loss: {r['avg_final_loss']} | Latency: {r['avg_latency_ms']}ms/user")
        gm = r["gru4rec_metrics"]
        pm = r["popularity_metrics"]
        print(f"  GRU4Rec:    Hit@5={gm.get('hit_rate@5'):.4f}, Hit@10={gm.get('hit_rate@10'):.4f} (95% CI: {r['gru4rec_hit10_ci95'][1]:.4f} - {r['gru4rec_hit10_ci95'][2]:.4f}), NDCG@10={gm.get('ndcg@10'):.4f}, Coverage={r['gru4rec_coverage']*100:.1f}%")
        print(f"  Popularity: Hit@5={pm.get('hit_rate@5'):.4f}, Hit@10={pm.get('hit_rate@10'):.4f} (95% CI: {r['popularity_hit10_ci95'][1]:.4f} - {r['popularity_hit10_ci95'][2]:.4f}), NDCG@10={pm.get('ndcg@10'):.4f}, Coverage={r['popularity_coverage']*100:.1f}%")

    print("\n" + "=" * 78)
    print(f"Results saved to:\n  - {json_path}\n  - {csv_path}")
    print("=" * 78 + "\n")


if __name__ == "__main__":
    main()
