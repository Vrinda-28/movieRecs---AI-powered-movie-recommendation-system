"""
Diversity Metrics and Diversity-Aware Re-Ranking for Recommender Systems.

Provides scientific measurement of:
1. Catalogue Coverage: Distinct recommended movies / Total catalogue size
2. Popularity Concentration: Share of recommendation slots in top-10% most-rated movies
3. Gini Coefficient of recommendation frequency across the catalogue
4. Shannon Entropy of recommendation distribution
5. Intra-List Diversity (ILD): Average pairwise genre Jaccard distance within user lists
6. Optional MMR (Maximal Marginal Relevance) re-ranker over candidate embeddings
"""

import math
from collections import Counter
from typing import Any, Callable, Dict, List, Optional, Sequence, Set, Tuple

import numpy as np

from app.core.config import settings
from app.services.recommender.explanation import (
    compute_cosine_similarity,
    get_candidate_embedding,
    parse_genres_set,
)


def compute_catalogue_coverage(
    all_recommendation_lists: Sequence[Sequence[int]],
    catalogue_size: int,
) -> float:
    """Compute proportion of unique items recommended across all users."""
    if catalogue_size <= 0:
        return 0.0
    unique_items = set()
    for recs in all_recommendation_lists:
        unique_items.update(recs)
    return float(len(unique_items) / catalogue_size)


def compute_popularity_concentration_top10(
    all_recommendation_lists: Sequence[Sequence[int]],
    top_10pct_item_ids: Set[int],
) -> float:
    """
    Compute percentage of total recommendation slots occupied by top-10% most popular items.
    """
    total_slots = sum(len(recs) for recs in all_recommendation_lists)
    if total_slots == 0:
        return 0.0
    top10_slots = sum(
        sum(1 for item in recs if item in top_10pct_item_ids)
        for recs in all_recommendation_lists
    )
    return float(top10_slots / total_slots)


def compute_gini_coefficient(
    item_counts: Sequence[int],
    catalogue_size: Optional[int] = None,
) -> float:
    """
    Compute Gini coefficient of recommendation distribution.
    0.0 = completely equal distribution
    1.0 = maximum concentration in a single item
    """
    counts = list(item_counts)
    if catalogue_size is not None and catalogue_size > len(counts):
        # Pad with zeros for catalogue items that were never recommended
        counts.extend([0] * (catalogue_size - len(counts)))

    n = len(counts)
    if n == 0 or sum(counts) == 0:
        return 0.0

    sorted_counts = np.sort(np.array(counts, dtype=np.float64))
    index = np.arange(1, n + 1)
    total_sum = np.sum(sorted_counts)
    return float(
        (2.0 * np.sum(index * sorted_counts) - (n + 1) * total_sum) / (n * total_sum)
    )


def compute_shannon_entropy(item_counts: Sequence[int]) -> float:
    """Compute Shannon entropy in bits (base 2) for recommendation frequencies."""
    total = sum(item_counts)
    if total == 0:
        return 0.0
    entropy = 0.0
    for count in item_counts:
        if count > 0:
            p = count / total
            entropy -= p * math.log2(p)
    return float(entropy)


def compute_intra_list_diversity(
    recommended_items: Sequence[int],
    item_genres_map: Dict[int, Set[str]],
) -> float:
    """
    Compute Intra-List Diversity (ILD) using pairwise genre Jaccard distance:
      d(i, j) = 1 - (|G_i ∩ G_j| / |G_i ∪ G_j|)
    """
    k = len(recommended_items)
    if k < 2:
        return 0.0

    pairwise_distances = []
    for i in range(k):
        genres_i = item_genres_map.get(recommended_items[i], set())
        for j in range(i + 1, k):
            genres_j = item_genres_map.get(recommended_items[j], set())
            union = genres_i | genres_j
            if not union:
                # If neither has genres, assume distance 1.0 (distinct)
                dist = 1.0
            else:
                intersection = genres_i & genres_j
                jaccard_sim = len(intersection) / len(union)
                dist = 1.0 - jaccard_sim
            pairwise_distances.append(dist)

    return float(np.mean(pairwise_distances)) if pairwise_distances else 0.0


def compute_dataset_diversity_summary(
    all_recommendation_lists: Sequence[Sequence[int]],
    catalogue_size: int,
    item_genres_map: Dict[int, Set[str]],
    training_item_counts: Optional[Dict[int, int]] = None,
) -> Dict[str, float]:
    """Compute full suite of diversity metrics over an evaluation user population."""
    freq_counter = Counter()
    for recs in all_recommendation_lists:
        freq_counter.update(recs)

    unique_items_recommended = len(freq_counter)
    coverage = compute_catalogue_coverage(all_recommendation_lists, catalogue_size)
    gini = compute_gini_coefficient(list(freq_counter.values()), catalogue_size)
    entropy = compute_shannon_entropy(list(freq_counter.values()))

    # Calculate top-10% popular items from training interactions
    top10_concentration = 0.0
    if training_item_counts:
        sorted_popular = sorted(
            training_item_counts.items(), key=lambda x: x[1], reverse=True
        )
        top_10_count = max(1, int(len(sorted_popular) * 0.10))
        top_10_ids = {item_id for item_id, _ in sorted_popular[:top_10_count]}
        top10_concentration = compute_popularity_concentration_top10(
            all_recommendation_lists, top_10_ids
        )

    # Intra-List Diversity across all users
    ild_scores = [
        compute_intra_list_diversity(recs, item_genres_map)
        for recs in all_recommendation_lists
        if len(recs) >= 2
    ]
    avg_ild = float(np.mean(ild_scores)) if ild_scores else 0.0

    return {
        "unique_recommended_count": unique_items_recommended,
        "catalogue_coverage": round(coverage, 4),
        "popularity_concentration_top10": round(top10_concentration, 4),
        "gini_index": round(gini, 4),
        "shannon_entropy": round(entropy, 4),
        "average_intra_list_diversity": round(avg_ild, 4),
    }


def mmr_rerank(
    candidate_ids: Sequence[int],
    model: Any,
    k: int = 10,
    lambda_param: float = settings.MMR_LAMBDA,
) -> List[int]:
    """
    Maximal Marginal Relevance (MMR) re-ranking over candidate embeddings.
    Balances relevance (rank order position) and diversity (dissimilarity to selected items).
    """
    if len(candidate_ids) <= k:
        return list(candidate_ids)

    embeddings = {}
    for mid in candidate_ids:
        emb = get_candidate_embedding(model, mid)
        embeddings[mid] = emb

    # Normalized relevance proxy from ranking position: score(i) = 1.0 - (rank / N)
    n_cands = len(candidate_ids)
    relevance_scores = {
        mid: 1.0 - (idx / n_cands) for idx, mid in enumerate(candidate_ids)
    }

    selected: List[int] = []
    remaining = list(candidate_ids)

    # Seed with top-ranked item
    selected.append(remaining.pop(0))

    while len(selected) < k and remaining:
        best_item = None
        best_mmr_score = -float("inf")

        for cand in remaining:
            rel = relevance_scores[cand]
            cand_emb = embeddings.get(cand)

            max_sim = 0.0
            if cand_emb is not None:
                sims = []
                for sel in selected:
                    sel_emb = embeddings.get(sel)
                    if sel_emb is not None:
                        sims.append(compute_cosine_similarity(cand_emb, sel_emb))
                if sims:
                    max_sim = max(sims)

            mmr_score = (lambda_param * rel) - ((1.0 - lambda_param) * max_sim)
            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_item = cand

        if best_item is not None:
            selected.append(best_item)
            remaining.remove(best_item)
        else:
            break

    return selected
