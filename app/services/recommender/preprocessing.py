"""
Preprocessing utilities for the GRU4Rec sequential recommender.

Training data pipeline:
  ratings_df -> get_movie_sequence_per_user -> ascending timestamp sort per user
             -> generate_examples_from_user_sequences (sliding window, right-pad with 0)
             -> create_tf_datasets

Inference context:
  user_movie_ids (already chronological ascending) -> prepare_user_context_for_prediction
  -> truncate to MAX_CONTEXT_LENGTH -> right-pad with 0 -> model input

Constants:
  MAX_CONTEXT_LENGTH = 10  (configurable via env)
  MIN_SEQUENCE_LENGTH = 3  (training minimum; also used as cold-start threshold at inference)
"""

import collections
from typing import Any, Dict, List

import pandas as pd
import tensorflow as tf

from app.core.config import settings

MAX_CONTEXT_LENGTH = settings.MAX_CONTEXT_LENGTH
MIN_SEQUENCE_LENGTH = settings.MIN_SEQUENCE_LENGTH
MIN_RATING_FILTER = 2


def get_movie_sequence_per_user(
    ratings_df: pd.DataFrame,
) -> Dict[int, List[Dict[str, Any]]]:
    """
    Build per-user movie interaction sequences from a flat ratings DataFrame.

    Each user's sequence is sorted ASCENDING by timestamp so the model
    always receives history in chronological order (oldest event first).
    This matches the inference ordering in predict.py.

    Args:
        ratings_df: DataFrame with columns user_id, movie_id, rating, timestamp.

    Returns:
        dict mapping user_id -> list of {movie_id, timestamp, rating} dicts,
        each list sorted ascending by timestamp.
    """
    sequences: Dict[int, list] = collections.defaultdict(list)

    for _, row in ratings_df.iterrows():
        user_id = int(row["user_id"])
        sequences[user_id].append(
            {
                "movie_id": int(row["movie_id"]),
                "timestamp": int(row["timestamp"]),
                "rating": float(row["rating"]),
            }
        )

    # Sort ASCENDING by timestamp for every user.
    # Invariant: sequence[0] is the oldest interaction, sequence[-1] the most recent.
    for user_id, context in sequences.items():
        context.sort(key=lambda x: x["timestamp"])
        sequences[user_id] = context

    return sequences


def generate_examples_from_user_sequences(
    sequences: Dict[int, List[Dict[str, Any]]],
    max_context_length: int = MAX_CONTEXT_LENGTH,
    padding_mode: str = settings.PADDING_MODE,
) -> List[Dict[str, Any]]:
    """
    Generate (context, label) training examples using a sliding window.

    For each position label_idx in [1, len(sequence)):
      - context = sequence[max(0, label_idx - max_context_length) : label_idx]
      - label   = sequence[label_idx]["movie_id"]
    Context is padded with movie_id=0 according to padding_mode ("right" or "left").

    Users with fewer than MIN_SEQUENCE_LENGTH ratings are excluded;
    their sequences cannot form valid training examples.
    """

    def _examples_for_user(sequence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        examples = []
        for label_idx in range(1, len(sequence)):
            start_idx = max(0, label_idx - max_context_length)
            context = sequence[start_idx:label_idx]

            padded_context = list(context)
            if padding_mode == "left":
                while len(padded_context) < max_context_length:
                    padded_context.insert(
                        0, {"movie_id": 0, "timestamp": 0, "rating": 0.0}
                    )
            else:  # "right"
                while len(padded_context) < max_context_length:
                    padded_context.append(
                        {"movie_id": 0, "timestamp": 0, "rating": 0.0}
                    )

            label_movie_id = int(sequence[label_idx]["movie_id"])
            context_movie_ids = [int(m["movie_id"]) for m in padded_context]

            examples.append(
                {
                    "context_movie_id": context_movie_ids,
                    "label_movie_id": label_movie_id,
                }
            )
        return examples

    all_examples = []
    for user_id, sequence in sequences.items():
        if len(sequence) < MIN_SEQUENCE_LENGTH:
            # Skip users without enough history to form training examples
            continue
        all_examples.extend(_examples_for_user(sequence))

    return all_examples


def create_tf_datasets(
    examples: List[Dict[str, Any]], batch_size: int, is_training: bool = True
):
    """Convert list of (context, label) examples to a tf.data.Dataset."""
    dataset_dict: Dict[str, list] = collections.defaultdict(list)
    for example in examples:
        dataset_dict["context_movie_id"].append(example["context_movie_id"])
        dataset_dict["label_movie_id"].append(example["label_movie_id"])

    context_movie_id_tf = tf.constant(dataset_dict["context_movie_id"], dtype=tf.int32)
    label_movie_id_tf = tf.constant(dataset_dict["label_movie_id"], dtype=tf.int32)

    dataset = tf.data.Dataset.from_tensor_slices(
        (context_movie_id_tf, label_movie_id_tf)
    )

    if is_training:
        dataset = dataset.shuffle(len(examples), reshuffle_each_iteration=True)

    dataset = dataset.batch(batch_size)
    dataset = dataset.cache()
    dataset = dataset.prefetch(tf.data.AUTOTUNE)

    return dataset


def prepare_user_context_for_prediction(
    user_movie_ids: List[int],
    max_context_length: int = MAX_CONTEXT_LENGTH,
    padding_mode: str = settings.PADDING_MODE,
) -> List[int]:
    """
    Prepare a user's chronological movie-id sequence for the GRU4Rec model.

    Invariant: user_movie_ids MUST already be in ascending timestamp order
    (oldest first). This function only truncates and pads; it does NOT sort.

    Steps:
      1. Truncate: keep only the last max_context_length IDs (most-recent context window).
      2. Pad: pad with 0 according to padding_mode to exactly max_context_length.
    """
    context = user_movie_ids[-max_context_length:]

    padded_context = list(context)
    if padding_mode == "left":
        while len(padded_context) < max_context_length:
            padded_context.insert(0, 0)
    else:  # "right"
        while len(padded_context) < max_context_length:
            padded_context.append(0)

    return padded_context
