from fastapi import APIRouter, Depends
from app.api import deps
from app.db import models
from app.worker.tasks import test_celery, train_recommendation_model_task

router = APIRouter()


@router.post("/trigger-test-celery/{word}")
async def trigger_test_task(
    word: str,
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Trigger a test Celery task. Admin only."""
    task = test_celery.delay(word)
    return {"message": "Test Celery task triggered", "task_id": task.id}


@router.post("/trigger-retrain-model")
async def trigger_retrain_task(
    current_user: models.User = Depends(deps.get_current_admin_user),
):
    """Trigger recommendation model retraining task in the background. Admin only."""
    task = train_recommendation_model_task.delay()
    return {"message": "Model retraining task triggered", "task_id": task.id}
