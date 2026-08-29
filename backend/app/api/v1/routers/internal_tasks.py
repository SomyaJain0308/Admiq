"""
Internal, secret-protected endpoints that run the periodic maintenance jobs
Celery beat used to schedule (process_closed_sessions_task, recompute_lead_scores_task,
check_and_send_reengagement_nudges_task). Triggered on a schedule by cron-job.org
instead of a persistent Celery worker + broker, since these are plain periodic sweeps,
not a real task queue.

Each endpoint calls the same async logic the Celery task called - nothing about the
actual work changes, only how it gets triggered.
"""

import logging

from fastapi import APIRouter, Header, HTTPException

from backend.app.config import get_settings
from backend.app.background_tasks.student_profile_tasks import _process_closed_sessions_async
from backend.app.background_tasks.lead_scoring_tasks import _recompute_lead_scores_async
from backend.app.background_tasks.reengagement_tasks import _check_and_send_reenagegement_nudges_async

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/tasks", tags=["Internal Tasks"])


def _verify_token(x_internal_token: str | None) -> None:
    settings = get_settings()
    if not settings.internal_task_token:
        # Fail closed: if no token is configured, refuse everything rather than
        # silently running unprotected.
        raise HTTPException(status_code=503, detail="internal_task_token not configured")
    if x_internal_token != settings.internal_task_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Internal-Token")


@router.post("/process-sessions")
async def process_sessions(x_internal_token: str | None = Header(default=None)):
    """Matches Celery beat's old 300s (5 min) schedule."""
    _verify_token(x_internal_token)
    await _process_closed_sessions_async()
    return {"ok": True, "task": "process_closed_sessions"}


@router.post("/reengagement-nudges")
async def reengagement_nudges(x_internal_token: str | None = Header(default=None)):
    """Matches Celery beat's old 600s (10 min) schedule."""
    _verify_token(x_internal_token)
    await _check_and_send_reenagegement_nudges_async()
    return {"ok": True, "task": "reengagement_nudges"}


@router.post("/recompute-lead-scores")
async def recompute_lead_scores(x_internal_token: str | None = Header(default=None)):
    """Matches Celery beat's old 86400s (24hr) schedule."""
    _verify_token(x_internal_token)
    await _recompute_lead_scores_async()
    return {"ok": True, "task": "recompute_lead_scores"}