"""
scripts/evaluate_diversity.py — Scientific Diversity & Fairness Measurement

Computes and tabulates:
1. Unique recommended movies count
2. Catalogue coverage (% of 3,952 movies)
3. Top-10% popularity concentration (% of recommendation slots)
4. Gini index of recommendation distribution (0=equal, 1=monopolized)
5. Shannon entropy (bits)
6. Intra-List Diversity (ILD) using genre Jaccard distance
7. Comparison between GRU4Rec, GRU4Rec + MMR, and Popularity Baseline
"""

import collections
import json
import logging
import os
import random
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import keras
import numpy as np
import pandas as pd
import tensorflow as tf

# Add project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.config import settings
from app.services.recommender.diversity import (
    compute_dataset_diversity_summary,
    compute_intra_list_diversity,
    mmr_rerank,
)
from app.services.recommender.evaluate import build_leave_last_out_splits
from app.services.recommender.explanation import parse_genres_set
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


def load_movies_genres_map() -> Tuple[Dict[int, Set[str]], int]:
    """Parse movies.dat to get movie_id -> set of genres."""
    genres_map: Dict[int, Set[str]] = {}
    max_id = 3952
    if MOVIES_FILE.exists():
        movies_df = pd.read_csv(
            MOVIES_FILE,
            sep="::",
            names=["movie_id", "title", "genres"],
            engine="python",
            encoding="latin-1",
        )
        max_id = int(movies_df["movie_id"].max())
        for _, row in movies_df.iterrows():
            genres_map[int(row["movie_id"])] = parse_genres_set(str(row.get("genres", "")))
    return genres_map, max_id


def load_movielens_data(num_users: int = 1000, seed: int = 42) -> Tuple[pd.DataFrame, int]:
    """Load ratings data for evaluation."""
    ratings_df = pd.read_csv(
        RATINGS_FILE,
        sep="::",
        names=["user_id", "movie_id", "rating", "timestamp"],
        engine="python",
    )
    user_counts = ratings_df["user_id"].value_counts()
    eligible_uids = user_counts[user_counts >= 20].index.tolist()
    rng = random.Random(seed)
    rng.shuffle(eligible_uids)
    
    selected_uids = set(eligible_uids[:num_users])
    sub_df = ratings_df[ratings_df["user_id"].isin(selected_uids)].copy()
    sub_df = sub_df[sub_df["rating"] >= MIN_RATING_FILTER]
    max_movie_id = int(ratings_df["movie_id"].max())
    return sub_df, max_movie_id


def run_diversity_evaluation(num_users: int = 1000, k: int = 10) -> Dict[str, Any]:
    ratings_df, max_movie_id = load_movielens_data(num_users=num_users)
    item_genres_map, catalogue_size = load_movies_genres_map()
    catalogue_size = max(catalogue_size, max_movie_id)
    
    train_sequences, test_instances, eligible_users = build_leave_last_out_splits(ratings_df)
    
    # Popularity items from training data
    train_counts: Dict[int, int] = collections.Counter()
    for seq in train_sequences.values():
        for item in seq:
            train_counts[item["movie_id"]] += 1
    sorted_popular = [mid for mid, _ in sorted(train_counts.items(), key=lambda x: x[1], reverse=True)]
    
    # Train model on train_sequences
    logger.info("Training GRU4Rec model for diversity evaluation...")
    random.seed(42)
    np.random.seed(42)
    tf.random.set_seed(42)
    
    train_examples = generate_examples_from_user_sequences(
        train_sequences,
        max_context_length=settings.MAX_CONTEXT_LENGTH,
        padding_mode="right",
    )
    train_ds = create_tf_datasets(train_examples, batch_size=256, is_training=True)
    
    model = SequentialRetrievalModel(
        movies_count=catalogue_size,
        embedding_dimension=32,
        gru_units=32,
        mask_zero=True,
        k=50,
    )
    model.compile(optimizer=keras.optimizers.AdamW(learning_rate=0.001))
    model(tf.zeros((1, settings.MAX_CONTEXT_LENGTH), dtype=tf.int32))
    model.fit(train_ds, epochs=10, verbose=0)
    
    # 1. Evaluate on test instances
    all_padded = [
        prepare_user_context_for_prediction(ctx, max_context_length=settings.MAX_CONTEXT_LENGTH, padding_mode="right")
        for _, ctx, _ in test_instances
    ]
    
    input_tensor = tf.constant(all_padded, dtype=tf.int32)
    output = model(input_tensor, training=False)
    pred_tensor = output["predictions"].numpy()
    
    gru_recs_all = []
    gru_mmr_recs_all = []
    pop_recs_all = []
    
    for i, (user_id, context_ids, target_movie_id) in enumerate(test_instances):
        history_set = set(context_ids)
        raw_preds = pred_tensor[i]
        
        # Standard GRU4Rec top-K
        valid_cands = [int(mid) for mid in raw_preds if int(mid) != 0 and int(mid) not in history_set]
        gru_topk = valid_cands[:k]
        if len(gru_topk) < k:
            for pmid in sorted_popular:
                if pmid not in history_set and pmid not in gru_topk:
                    gru_topk.append(pmid)
                if len(gru_topk) >= k:
                    break
        gru_recs_all.append(gru_topk)
        
        # MMR-Reranked GRU4Rec top-K
        if len(valid_cands) > k:
            mmr_topk = mmr_rerank(valid_cands[:30], model, k=k, lambda_param=0.7)
        else:
            mmr_topk = list(gru_topk)
        gru_mmr_recs_all.append(mmr_topk)
        
        # Popularity top-K
        pop_topk = [pmid for pmid in sorted_popular if pmid not in history_set][:k]
        pop_recs_all.append(pop_topk)
        
    gru_diversity = compute_dataset_diversity_summary(
        gru_recs_all, catalogue_size, item_genres_map, train_counts
    )
    gru_mmr_diversity = compute_dataset_diversity_summary(
        gru_mmr_recs_all, catalogue_size, item_genres_map, train_counts
    )
    pop_diversity = compute_dataset_diversity_summary(
        pop_recs_all, catalogue_size, item_genres_map, train_counts
    )
    
    # Measure Hit Rate @ 10 for each
    def get_hit_rate(recs_list):
        hits = sum(1 for idx, (_, _, target_id) in enumerate(test_instances) if target_id in recs_list[idx])
        return round(hits / len(test_instances), 4)
        
    results = {
        "num_users_evaluated": len(test_instances),
        "catalogue_size": catalogue_size,
        "k": k,
        "popularity_baseline": {
            **pop_diversity,
            "hit_rate_at_10": get_hit_rate(pop_recs_all),
        },
        "gru4rec_standard": {
            **gru_diversity,
            "hit_rate_at_10": get_hit_rate(gru_recs_all),
        },
        "gru4rec_mmr_reranked": {
            **gru_mmr_diversity,
            "hit_rate_at_10": get_hit_rate(gru_mmr_recs_all),
        },
    }
    
    output_dir = Path("models_store/evaluation")
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "diversity_summary.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2)
        
    logger.info(f"Diversity summary saved to {json_path}")
    print("\n" + "=" * 70)
    print("                DIVERSITY & FAIRNESS BENCHMARK")
    print("=" * 70)
    print(f"Users Evaluated: {len(test_instances)} | Catalogue: {catalogue_size} items | K={k}\n")
    print(f"{'Metric':<30} | {'Popularity':<12} | {'GRU4Rec':<12} | {'GRU4Rec + MMR':<12}")
    print("-" * 70)
    print(f"{'Unique Items Recommended':<30} | {pop_diversity['unique_recommended_count']:<12} | {gru_diversity['unique_recommended_count']:<12} | {gru_mmr_diversity['unique_recommended_count']:<12}")
    print(f"{'Catalogue Coverage':<30} | {pop_diversity['catalogue_coverage']*100:.1f}%{'':<7} | {gru_diversity['catalogue_coverage']*100:.1f}%{'':<7} | {gru_mmr_diversity['catalogue_coverage']*100:.1f}%")
    print(f"{'Top-10% Pop Concentration':<30} | {pop_diversity['popularity_concentration_top10']*100:.1f}%{'':<7} | {gru_diversity['popularity_concentration_top10']*100:.1f}%{'':<7} | {gru_mmr_diversity['popularity_concentration_top10']*100:.1f}%")
    print(f"{'Gini Coefficient':<30} | {pop_diversity['gini_index']:<12.4f} | {gru_diversity['gini_index']:<12.4f} | {gru_mmr_diversity['gini_index']:<12.4f}")
    print(f"{'Shannon Entropy (bits)':<30} | {pop_diversity['shannon_entropy']:<12.2f} | {gru_diversity['shannon_entropy']:<12.2f} | {gru_mmr_diversity['shannon_entropy']:<12.2f}")
    print(f"{'Intra-List Diversity (ILD)':<30} | {pop_diversity['average_intra_list_diversity']:<12.4f} | {gru_diversity['average_intra_list_diversity']:<12.4f} | {gru_mmr_diversity['average_intra_list_diversity']:<12.4f}")
    print(f"{'Hit Rate@10 (Accuracy)':<30} | {results['popularity_baseline']['hit_rate_at_10']*100:.2f}%{'':<6} | {results['gru4rec_standard']['hit_rate_at_10']*100:.2f}%{'':<6} | {results['gru4rec_mmr_reranked']['hit_rate_at_10']*100:.2f}%")
    print("=" * 70 + "\n")
    
    return results


if __name__ == "__main__":
    run_diversity_evaluation()
