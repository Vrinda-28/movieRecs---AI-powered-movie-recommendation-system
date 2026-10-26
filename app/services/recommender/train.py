"""
Model training pipeline for GRU4Rec sequential recommendation.

Features:
  - Fully configurable hyperparameters via settings, environment variables, or function arguments / CLI.
  - Early stopping on validation loss with restore_best_weights=True.
  - Configurable zero-masking (mask_zero=True) and padding modes ('right' vs 'left').
  - Atomic model saving with temporary file replacement.
  - Model metadata sidecar JSON output (*.keras.json) for lineage, reproducibility, and admin auditing.
"""

import argparse
import asyncio
import json
import logging
import os
import random
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

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
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_git_commit_hash() -> str:
    try:
        res = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        )
        return res.strip()
    except Exception:
        return "unversioned"


def set_reproducibility_seeds(seed: int = 42):
    random.seed(seed)
    np.random.seed(seed)
    tf.random.set_seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)


async def train_model(
    db: AsyncSession,
    epochs: Optional[int] = None,
    batch_size: Optional[int] = None,
    learning_rate: Optional[float] = None,
    embedding_dim: Optional[int] = None,
    gru_units: Optional[int] = None,
    max_context_length: Optional[int] = None,
    validation_split: Optional[float] = None,
    patience: Optional[int] = None,
    mask_zero: Optional[bool] = None,
    padding_mode: Optional[str] = None,
    seed: Optional[int] = None,
    model_path: Optional[str] = None,
    save_sidecar: bool = True,
    dataset_name: str = "MovieLens-1M",
) -> Dict[str, Any]:
    """
    Trains the GRU4Rec Sequential Retrieval model with validation monitoring and sidecar tracking.
    """
    # 1. Resolve hyperparameters
    _epochs = epochs if epochs is not None else settings.EPOCHS
    _batch_size = batch_size if batch_size is not None else settings.BATCH_SIZE
    _learning_rate = (
        learning_rate if learning_rate is not None else settings.LEARNING_RATE
    )
    _embedding_dim = (
        embedding_dim if embedding_dim is not None else settings.EMBEDDING_DIM
    )
    _gru_units = gru_units if gru_units is not None else settings.GRU_UNITS
    _max_context_length = (
        max_context_length
        if max_context_length is not None
        else settings.MAX_CONTEXT_LENGTH
    )
    _val_split = (
        validation_split if validation_split is not None else settings.VALIDATION_SPLIT
    )
    _patience = patience if patience is not None else settings.EARLY_STOPPING_PATIENCE
    _mask_zero = mask_zero if mask_zero is not None else settings.MASK_ZERO
    _padding_mode = padding_mode if padding_mode is not None else settings.PADDING_MODE
    _seed = seed if seed is not None else 42
    _target_model_path = model_path if model_path is not None else settings.MODEL_PATH

    set_reproducibility_seeds(_seed)

    logger.info("=" * 70)
    logger.info("STARTING GRU4REC MODEL TRAINING")
    logger.info(
        f"Config: epochs={_epochs}, batch_size={_batch_size}, lr={_learning_rate}, "
        f"embed_dim={_embedding_dim}, gru_units={_gru_units}, max_context={_max_context_length}, "
        f"mask_zero={_mask_zero}, padding_mode={_padding_mode}, val_split={_val_split}, seed={_seed}"
    )
    logger.info("=" * 70)

    # 2. Fetch all ratings from DB
    raw_ratings_data: List[Rating] = await crud.rating.get_all_ratings_for_training(db)
    if not raw_ratings_data:
        logger.warning("No ratings data found in the database. Skipping training.")
        return {"error": "No ratings found"}

    data_for_pandas = [
        {
            "user_id": r.user_id,
            "movie_id": r.movie_id,
            "rating": r.rating,
            "timestamp": r.timestamp,
        }
        for r in raw_ratings_data
    ]
    ratings_df = pd.DataFrame(data_for_pandas)
    total_raw_ratings = len(ratings_df)
    unique_users_raw = ratings_df["user_id"].nunique()

    ratings_df = ratings_df[ratings_df["rating"] >= MIN_RATING_FILTER]
    if ratings_df.empty:
        logger.warning(f"No ratings left after filtering >= {MIN_RATING_FILTER}.")
        return {"error": "No ratings after filter"}

    # 3. Build chronological sequences and sliding window examples
    user_sequences = get_movie_sequence_per_user(ratings_df)
    eligible_users = [
        u for u, seq in user_sequences.items() if len(seq) >= MIN_SEQUENCE_LENGTH
    ]

    examples = generate_examples_from_user_sequences(
        user_sequences,
        max_context_length=_max_context_length,
        padding_mode=_padding_mode,
    )
    if not examples:
        logger.warning("No training examples generated.")
        return {"error": "No training examples"}

    logger.info(
        f"Dataset summary: {unique_users_raw} users ({len(eligible_users)} eligible >= {MIN_SEQUENCE_LENGTH}), "
        f"{total_raw_ratings} ratings -> {len(examples)} sliding-window examples."
    )

    # 4. Train / Validation split (randomized on examples with fixed seed)
    rng = random.Random(_seed)
    rng.shuffle(examples)
    split_index = int((1.0 - _val_split) * len(examples))
    train_examples = examples[:split_index]
    val_examples = examples[split_index:]

    if not train_examples:
        logger.warning("No train examples after split.")
        return {"error": "Empty train examples"}

    train_ds = create_tf_datasets(train_examples, _batch_size, is_training=True)
    val_ds = (
        create_tf_datasets(val_examples, _batch_size, is_training=False)
        if val_examples
        else None
    )

    # 5. Determine movies_count vocabulary ceiling
    max_internal_movie_id_from_db = await crud.movie.get_max_internal_movie_id(db)
    max_internal_movie_id_in_ratings = (
        ratings_df["movie_id"].max() if not ratings_df.empty else 0
    )

    movies_count = 0
    if max_internal_movie_id_from_db is not None:
        movies_count = max(movies_count, int(max_internal_movie_id_from_db))
    if max_internal_movie_id_in_ratings > 0:
        movies_count = max(movies_count, int(max_internal_movie_id_in_ratings))

    if movies_count == 0:
        logger.error("movies_count is 0. Cannot train model.")
        return {"error": "Zero movies count"}

    logger.info(
        f"Model Vocabulary Capacity: {movies_count} movies (internal IDs 1..{movies_count})"
    )

    # 6. Instantiate and build model
    model = SequentialRetrievalModel(
        movies_count=movies_count,
        embedding_dimension=_embedding_dim,
        gru_units=_gru_units,
        mask_zero=_mask_zero,
    )
    model.compile(optimizer=keras.optimizers.AdamW(learning_rate=_learning_rate))

    # Build graph with dummy input
    model(tf.zeros((1, _max_context_length), dtype=tf.int32))

    # 7. Callbacks: EarlyStopping on validation loss
    callbacks = []
    if val_ds and _patience > 0:
        early_stopping = keras.callbacks.EarlyStopping(
            monitor="val_loss",
            patience=_patience,
            restore_best_weights=True,
            verbose=1,
        )
        callbacks.append(early_stopping)

    # 8. Model training
    start_time = time.time()
    fit_kwargs = {"validation_data": val_ds} if val_ds else {}
    history = model.fit(
        train_ds,
        epochs=_epochs,
        callbacks=callbacks,
        verbose=1,
        **fit_kwargs,
    )
    training_duration = time.time() - start_time

    history_dict = {k: [float(val) for val in v] for k, v in history.history.items()}
    actual_epochs_run = len(history_dict.get("loss", []))
    final_train_loss = (
        float(history_dict["loss"][-1]) if "loss" in history_dict else None
    )
    final_val_loss = (
        float(history_dict["val_loss"][-1]) if "val_loss" in history_dict else None
    )

    logger.info(
        f"Training complete in {training_duration:.2f}s across {actual_epochs_run} epochs. "
        f"Train Loss: {final_train_loss:.4f}, Val Loss: {final_val_loss if final_val_loss is not None else 'N/A'}"
    )

    # 9. Verification & Safe Atomic Replacement
    model_dir = os.path.dirname(_target_model_path)
    if model_dir:
        os.makedirs(model_dir, exist_ok=True)

    versions_dir = Path(model_dir if model_dir else "models_store") / "versions"
    versions_dir.mkdir(parents=True, exist_ok=True)

    if _target_model_path.endswith(".keras"):
        tmp_model_path = _target_model_path[:-6] + f"_tmp_{int(time.time())}.keras"
    else:
        tmp_model_path = f"{_target_model_path}_tmp_{int(time.time())}.keras"

    try:
        # Save to temporary path first
        model.save(tmp_model_path)

        # Verification step: ensure newly saved artifact loads and runs sample prediction
        is_valid = verify_model_artifact(
            tmp_model_path, context_length=_max_context_length
        )
        if not is_valid:
            raise ValueError(
                f"Model verification failed for candidate model at {tmp_model_path}. "
                "The previous valid model was preserved without changes."
            )

        # Atomically replace live model
        os.replace(tmp_model_path, _target_model_path)
        model_size_bytes = os.path.getsize(_target_model_path)
        logger.info(
            f"Model verified and atomically deployed to {_target_model_path} ({model_size_bytes / (1024*1024):.2f} MB)"
        )
    except Exception as e:
        logger.error(f"Error in model verification/deployment: {e}", exc_info=True)
        if os.path.exists(tmp_model_path):
            try:
                os.remove(tmp_model_path)
            except Exception:
                pass
        raise

    # 10. Save metadata sidecar JSON
    version_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{get_git_commit_hash()[:7]}"
    version_filename = f"gru4rec_{version_id}.keras"

    sidecar_data = {
        "dataset_name": dataset_name,
        "version_id": version_id,
        "version_filename": version_filename,
        "raw_users_count": unique_users_raw,
        "eligible_users_count": len(eligible_users),
        "total_interactions_count": total_raw_ratings,
        "movies_vocabulary_count": movies_count,
        "training_examples_count": len(train_examples),
        "validation_examples_count": len(val_examples),
        "window_length": _max_context_length,
        "embedding_dim": _embedding_dim,
        "gru_units": _gru_units,
        "epochs_requested": _epochs,
        "epochs_actual": actual_epochs_run,
        "batch_size": _batch_size,
        "learning_rate": _learning_rate,
        "optimizer": "AdamW",
        "loss_function": "CategoricalCrossentropy",
        "mask_zero": _mask_zero,
        "padding_mode": _padding_mode,
        "validation_strategy": f"Random split ({_val_split * 100:.0f}%)",
        "early_stopping_patience": _patience,
        "seed": _seed,
        "training_duration_seconds": round(training_duration, 2),
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit_hash": get_git_commit_hash(),
        "model_file_name": os.path.basename(_target_model_path),
        "model_file_size_bytes": model_size_bytes,
        "final_train_loss": round(final_train_loss, 4) if final_train_loss else None,
        "final_val_loss": round(final_val_loss, 4) if final_val_loss else None,
        "loss_history": history_dict,
    }

    if save_sidecar:
        sidecar_path = f"{_target_model_path}.json"
        with open(sidecar_path, "w") as f:
            json.dump(sidecar_data, f, indent=2)
        logger.info(f"Model metadata sidecar saved to {sidecar_path}")

        # Save archived version copy in versions/
        try:
            import shutil

            archived_model_path = versions_dir / version_filename
            archived_sidecar_path = versions_dir / f"{version_filename}.json"
            shutil.copy2(_target_model_path, archived_model_path)
            with open(archived_sidecar_path, "w") as f:
                json.dump(sidecar_data, f, indent=2)

            # Update active version marker
            active_info = {
                "active_version": version_filename,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "live_path": _target_model_path,
                "sidecar": sidecar_data,
            }
            with open(versions_dir / "active_version.json", "w") as f:
                json.dump(active_info, f, indent=2)

            # Cleanup older versions keeping latest 10
            all_versions = sorted(
                versions_dir.glob("gru4rec_*.keras"), key=lambda p: p.stat().st_mtime
            )
            if len(all_versions) > 10:
                for old_ver in all_versions[:-10]:
                    try:
                        old_ver.unlink(missing_ok=True)
                        Path(str(old_ver) + ".json").unlink(missing_ok=True)
                    except Exception:
                        pass
        except Exception as e:
            logger.warning(f"Version archival notice: {e}")

    return sidecar_data


def verify_model_artifact(
    model_path: str, context_length: int = settings.MAX_CONTEXT_LENGTH
) -> bool:
    """Verifies that a model artifact file loads and produces valid predictions."""
    try:
        loaded = keras.models.load_model(
            model_path,
            custom_objects={"SequentialRetrievalModel": SequentialRetrievalModel},
        )
        dummy_input = tf.zeros((1, context_length), dtype=tf.int32)
        out = loaded(dummy_input, training=False)
        if "predictions" not in out:
            return False
        preds = out["predictions"]
        if hasattr(preds, "numpy"):
            preds_np = preds.numpy()
        else:
            preds_np = np.array(preds)
        return bool(preds_np.shape[0] == 1 and preds_np.shape[1] > 0)
    except Exception as e:
        logger.error(f"Model verification failed for {model_path}: {e}")
        return False


def list_model_versions(versions_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Lists all archived model versions with their metadata and active flag."""
    if versions_dir is None:
        model_dir = os.path.dirname(settings.MODEL_PATH)
        versions_dir = Path(model_dir if model_dir else "models_store") / "versions"

    if not versions_dir.exists():
        return []

    active_version_name = None
    active_marker = versions_dir / "active_version.json"
    if active_marker.exists():
        try:
            with open(active_marker, "r") as f:
                active_info = json.load(f)
                active_version_name = active_info.get("active_version")
        except Exception:
            pass

    versions_list = []
    for model_file in sorted(
        versions_dir.glob("gru4rec_*.keras"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    ):
        sidecar_path = Path(str(model_file) + ".json")
        sidecar_data = {}
        if sidecar_path.exists():
            try:
                with open(sidecar_path, "r") as f:
                    sidecar_data = json.load(f)
            except Exception:
                pass

        versions_list.append(
            {
                "version_filename": model_file.name,
                "is_active": model_file.name == active_version_name,
                "created_at": datetime.fromtimestamp(
                    model_file.stat().st_mtime, timezone.utc
                ).isoformat(),
                "size_bytes": model_file.stat().st_size,
                "metadata": sidecar_data,
            }
        )
    return versions_list


def rollback_model_version(
    version_filename: str,
    target_path: Optional[str] = None,
    versions_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Rolls back the live model to a specified archived version."""
    _target_path = target_path if target_path is not None else settings.MODEL_PATH
    model_dir = os.path.dirname(_target_path)
    if versions_dir is None:
        versions_dir = Path(model_dir if model_dir else "models_store") / "versions"

    version_model_path = versions_dir / version_filename
    if not version_model_path.exists():
        raise FileNotFoundError(
            f"Version file {version_filename} not found in {versions_dir}"
        )

    # Verify version before deploying
    if not verify_model_artifact(str(version_model_path)):
        raise ValueError(
            f"Rollback target {version_filename} failed verification check."
        )

    import shutil

    # Copy version file over live target path
    shutil.copy2(version_model_path, _target_path)

    # Copy sidecar
    version_sidecar = versions_dir / f"{version_filename}.json"
    sidecar_data = {}
    if version_sidecar.exists():
        shutil.copy2(version_sidecar, f"{_target_path}.json")
        try:
            with open(version_sidecar, "r") as f:
                sidecar_data = json.load(f)
        except Exception:
            pass

    # Update active marker
    active_info = {
        "active_version": version_filename,
        "activated_at": datetime.now(timezone.utc).isoformat(),
        "live_path": _target_path,
        "sidecar": sidecar_data,
    }
    with open(versions_dir / "active_version.json", "w") as f:
        json.dump(active_info, f, indent=2)

    logger.info(f"Successfully rolled back live model to {version_filename}")
    return {
        "status": "success",
        "rolled_back_to": version_filename,
        "activated_at": active_info["activated_at"],
        "metadata": sidecar_data,
    }


def set_training_status(
    status: str,
    task_id: Optional[str] = None,
    start_time: Optional[str] = None,
    finish_time: Optional[str] = None,
    error_text: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
):
    """Persists current or latest training status to disk."""
    status_file = Path("models_store/training_status.json")
    status_file.parent.mkdir(parents=True, exist_ok=True)

    current_data = {}
    if status_file.exists():
        try:
            with open(status_file, "r") as f:
                current_data = json.load(f)
        except Exception:
            current_data = {}

    current_data.update(
        {
            "status": status,
            "task_id": task_id if task_id is not None else current_data.get("task_id"),
            "start_time": (
                start_time if start_time is not None else current_data.get("start_time")
            ),
            "finish_time": (
                finish_time
                if finish_time is not None
                else current_data.get("finish_time")
            ),
            "error_text": error_text,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    if metadata:
        current_data["metadata"] = metadata

    with open(status_file, "w") as f:
        json.dump(current_data, f, indent=2)


def get_training_status_record() -> Dict[str, Any]:
    """Retrieves the latest training status record from disk."""
    status_file = Path("models_store/training_status.json")
    if not status_file.exists():
        return {
            "status": "idle",
            "task_id": None,
            "start_time": None,
            "finish_time": None,
            "error_text": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    try:
        with open(status_file, "r") as f:
            return json.load(f)
    except Exception:
        return {"status": "idle", "task_id": None, "error_text": "Corrupt status file"}


def parse_args():
    parser = argparse.ArgumentParser(description="Train GRU4Rec Recommendation Model")
    parser.add_argument(
        "--epochs", type=int, default=None, help="Number of epochs to train"
    )
    parser.add_argument("--batch-size", type=int, default=None, help="Batch size")
    parser.add_argument("--lr", type=float, default=None, help="Learning rate")
    parser.add_argument(
        "--embed-dim", type=int, default=None, help="Embedding dimension"
    )
    parser.add_argument("--gru-units", type=int, default=None, help="GRU units")
    parser.add_argument(
        "--window", type=int, default=None, help="Max context length window"
    )
    parser.add_argument(
        "--val-split", type=float, default=None, help="Validation split fraction"
    )
    parser.add_argument(
        "--patience", type=int, default=None, help="Early stopping patience"
    )
    parser.add_argument(
        "--mask-zero",
        action="store_true",
        default=None,
        help="Enable mask_zero in Embedding",
    )
    parser.add_argument(
        "--padding", choices=["right", "left"], default=None, help="Padding mode"
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Random seed for reproducibility"
    )
    parser.add_argument(
        "--model-path", type=str, default=None, help="Destination model path"
    )
    return parser.parse_args()


async def main():
    args = parse_args()
    async with AsyncSessionLocal() as db:
        await train_model(
            db=db,
            epochs=args.epochs,
            batch_size=args.batch_size,
            learning_rate=args.lr,
            embedding_dim=args.embed_dim,
            gru_units=args.gru_units,
            max_context_length=args.window,
            validation_split=args.val_split,
            patience=args.patience,
            mask_zero=args.mask_zero,
            padding_mode=args.padding,
            seed=args.seed,
            model_path=args.model_path,
        )


if __name__ == "__main__":
    asyncio.run(main())
