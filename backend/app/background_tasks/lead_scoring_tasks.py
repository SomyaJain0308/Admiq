import asyncio 
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.services.lead_scoring import compute_lead_score


logger = logging.getLogger(__name__)

BATCH_SIZE = 200


@celery_app.task
def recompute_lead_scores_task():
    asyncio.run(_recompute_lead_scores_async())