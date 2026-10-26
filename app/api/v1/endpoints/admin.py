"""
Admin API Endpoints.

Provides administrative controls, system health diagnostics, live metrics,
training status tracking, model versioning, rollback, and catalogue management.
All endpoints require administrator authorization (enforced via deps.get_current_admin_user).
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import deps
from app.core.config import settings
from app.db import crud, models
from app.services.recommender.train import (
    get_training_status_record,
    list_model_versions,
    rollback_model_version,
    set_training_status,
)
from app.worker.celery_app import celery_app
from app.worker.tasks import test_celery, train_recommendation_model_task

logger = logging.getLogger(__name__)

router = APIRouter()


class RollbackRequest(BaseModel):
    version_name: str


@router.post("/trigger-test-celery/{word}")
async def trigger_test_task(
    word: str,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Trigger a test Celery task. Admin only."""
    try:
        task = test_celery.delay(word)
        return {"message": "Test Celery task triggered", "task_id": task.id}
    except Exception as e:
        logger.error(f"Celery unavailable: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Celery/Redis broker is currently unreachable: {str(e)}",
        )


@router.post("/trigger-retrain-model")
async def trigger_retrain_task(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Trigger recommendation model retraining task in the background. Admin only."""
    try:
        task = train_recommendation_model_task.delay()
        task_id = str(task.id)
        start_iso = datetime.now(timezone.utc).isoformat()
        set_training_status(status="queued", task_id=task_id, start_time=start_iso)
        return {
            "message": "Model retraining task triggered",
            "task_id": task_id,
            "status": "queued",
        }
    except Exception as e:
        logger.error(f"Failed to queue retraining task in Celery: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Background worker is unreachable. Ensure Redis and Celery worker are running: {str(e)}",
        )


@router.get("/training-status/latest")
async def get_latest_training_status(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Get the status of the latest training run."""
    record = get_training_status_record()
    task_id = record.get("task_id")

    # Cross-reference with Celery state if available
    if task_id and task_id != "manual":
        try:
            res = AsyncResult(task_id, app=celery_app)
            celery_state = res.status
            if celery_state == "PENDING" and record.get("status") != "running":
                record["status"] = "queued"
            elif celery_state == "STARTED":
                record["status"] = "running"
            elif celery_state == "SUCCESS":
                record["status"] = "successful"
            elif celery_state in ("FAILURE", "REVOKED"):
                record["status"] = "failed"
        except Exception:
            pass  # Fall back to file-persisted state

    return record


@router.get("/training-status/{task_id}")
async def get_task_training_status(
    task_id: str,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """
    Get the status of a specific training task ID.
    Mapped to: idle | queued | running | successful | failed.
    """
    record = get_training_status_record()
    current_status = "idle"
    error_text = None

    try:
        res = AsyncResult(task_id, app=celery_app)
        celery_state = res.status

        state_map = {
            "PENDING": "queued",
            "STARTED": "running",
            "SUCCESS": "successful",
            "FAILURE": "failed",
            "RETRY": "failed",
            "REVOKED": "failed",
        }
        current_status = state_map.get(celery_state, "idle")
        if res.failed():
            error_text = str(res.result)
    except Exception as e:
        logger.warning(f"Could not reach Celery for task {task_id}: {e}")
        if record.get("task_id") == task_id:
            current_status = record.get("status", "idle")
            error_text = record.get("error_text")

    return {
        "task_id": task_id,
        "status": current_status,
        "start_time": (
            record.get("start_time") if record.get("task_id") == task_id else None
        ),
        "finish_time": (
            record.get("finish_time") if record.get("task_id") == task_id else None
        ),
        "error_text": error_text
        or (record.get("error_text") if record.get("task_id") == task_id else None),
        "metadata": (
            record.get("metadata") if record.get("task_id") == task_id else None
        ),
    }


@router.get("/system-health")
async def get_system_health(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Real health check for DB, Redis, Celery worker, and Live Recommender Model."""
    # 1. Database check
    db_healthy = False
    try:
        await db.execute(select(1))
        db_healthy = True
    except Exception as e:
        logger.error(f"DB Health check failed: {e}")

    # 2. Redis check
    redis_healthy = False
    try:
        import redis

        r = redis.Redis(
            host=settings.REDIS_HOST, port=settings.REDIS_PORT, socket_connect_timeout=1
        )
        redis_healthy = r.ping()
    except Exception:
        redis_healthy = False

    # 3. Celery worker check
    celery_worker_healthy = False
    if redis_healthy:
        try:
            insp = celery_app.control.inspect(timeout=0.2)
            if insp:
                active = insp.active()
                celery_worker_healthy = bool(active)
        except Exception:
            celery_worker_healthy = False

    # 4. Model file check
    model_path = Path(settings.MODEL_PATH)
    model_exists = model_path.exists()
    model_mtime = (
        datetime.fromtimestamp(model_path.stat().st_mtime, timezone.utc).isoformat()
        if model_exists
        else None
    )

    return {
        "database": {
            "healthy": db_healthy,
            "type": "PostgreSQL" if "postgresql" in settings.DATABASE_URL else "SQLite",
        },
        "redis": {
            "healthy": redis_healthy,
            "host": settings.REDIS_HOST,
            "port": settings.REDIS_PORT,
        },
        "celery_worker": {"healthy": celery_worker_healthy},
        "recommender_model": {
            "healthy": model_exists,
            "path": settings.MODEL_PATH,
            "last_modified": model_mtime,
            "size_bytes": model_path.stat().st_size if model_exists else 0,
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/database-counts")
async def get_database_counts(
    db: AsyncSession = Depends(deps.get_db),
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Returns actual row counts from PostgreSQL tables."""
    users_count = await db.scalar(select(func.count(models.User.id))) or 0
    movies_count = await db.scalar(select(func.count(models.Movie.id))) or 0
    ratings_count = await db.scalar(select(func.count(models.Rating.id))) or 0
    reviews_count = await db.scalar(select(func.count(models.Review.id))) or 0
    watchlist_count = await db.scalar(select(func.count(models.Watchlist.id))) or 0
    interactions_count = await db.scalar(select(func.count(models.Interaction.id))) or 0

    return {
        "users": users_count,
        "movies": movies_count,
        "ratings": ratings_count,
        "reviews": reviews_count,
        "watchlist_entries": watchlist_count,
        "interactions": interactions_count,
    }


@router.get("/model-info")
async def get_live_model_info(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Returns the live model hyperparameters and lineage from its sidecar JSON."""
    sidecar_path = Path(f"{settings.MODEL_PATH}.json")
    if not sidecar_path.exists():
        return {
            "status": "NO_SIDECAR",
            "message": "Live model has no sidecar metadata file.",
            "model_path": settings.MODEL_PATH,
        }
    try:
        with open(sidecar_path, "r") as f:
            sidecar_data = json.load(f)
        return {
            "status": "AVAILABLE",
            "model_path": settings.MODEL_PATH,
            "sidecar": sidecar_data,
        }
    except Exception as e:
        return {"status": "ERROR", "message": str(e)}


@router.get("/latest-evaluation")
async def get_latest_evaluation(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """
    Returns latest leak-free offline evaluation results (GRU4Rec vs Popularity at K=5 and K=10).
    Reads strictly from stored JSON files; returns 'NOT YET MEASURED' if no evaluation exists.
    """
    eval_dir = Path("models_store/evaluation")
    summary_path = eval_dir / "experiments_summary.json"

    if summary_path.exists():
        try:
            with open(summary_path, "r") as f:
                experiments = json.load(f)
            # Find the primary tuned benchmark or latest experiment
            primary_exp = experiments[2] if len(experiments) > 2 else experiments[-1]
            return {
                "status": "MEASURED",
                "experiment_name": primary_exp.get("experiment_name"),
                "users_evaluated": primary_exp.get("users_evaluated"),
                "total_ratings": primary_exp.get("total_ratings"),
                "gru4rec": primary_exp.get("gru4rec_metrics"),
                "gru4rec_hit10_ci95": primary_exp.get("gru4rec_hit10_ci95"),
                "gru4rec_ndcg10_ci95": primary_exp.get("gru4rec_ndcg10_ci95"),
                "gru4rec_coverage": primary_exp.get("gru4rec_coverage"),
                "popularity": primary_exp.get("popularity_metrics"),
                "popularity_hit10_ci95": primary_exp.get("popularity_hit10_ci95"),
                "popularity_coverage": primary_exp.get("popularity_coverage"),
                "all_experiments": experiments,
            }
        except Exception as e:
            logger.error(f"Error parsing experiments summary: {e}")

    # Check for timestamped files
    eval_files = (
        sorted(eval_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        if eval_dir.exists()
        else []
    )
    if eval_files:
        try:
            with open(eval_files[0], "r") as f:
                data = json.load(f)
            return {"status": "MEASURED", "data": data}
        except Exception:
            pass

    return {
        "status": "NOT YET MEASURED",
        "message": "No offline evaluation artifacts found in models_store/evaluation/",
    }


@router.get("/models/versions")
async def get_model_versions(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Lists archived model versions in models_store/versions/."""
    versions = list_model_versions()
    return {"versions": versions, "total_count": len(versions)}


@router.post("/models/rollback")
async def rollback_to_version(
    req: RollbackRequest,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Rolls back the live recommender model to a specified archived version."""
    try:
        res = rollback_model_version(req.version_name)
        return res
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Rollback error: {str(e)}")
