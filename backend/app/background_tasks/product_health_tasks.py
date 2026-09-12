"""
Periodic Celery task that refreshes the two product-health gauges from
monitoring/api_metrics.py: ACTIVE_STUDENTS_7D and DOCUMENTS_INDEXED. These
are Gauges rather than Counters because they're a current snapshot ("how
many right now"), not a running total - each run just overwrites the
previous value per college_id, following the same pattern as
LOW_CONFIDENCE_QUERIES_OPEN in monitoring/low_confidence.py.

Deliberately college-scoped labels rather than one global number, same
reasoning as everywhere else in this codebase's metrics: a single college
going quiet (or a single college's ingestion pipeline breaking) should be
visible on its own, not averaged away into a fleet-wide total.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func, distinct

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal
from backend.app.models.Message import Message
from backend.app.models.Document import Document
from backend.app.models.College import College
from backend.app.monitoring.api_metrics import ACTIVE_STUDENTS_7D, DOCUMENTS_INDEXED

logger = logging.getLogger(__name__)

ACTIVE_WINDOW_DAYS = 7


@celery_app.task
def refresh_product_health_gauges_task():
    asyncio.run(_refresh_product_health_gauges_async())


async def _refresh_product_health_gauges_async():
    try:
        async with AsyncSessionLocal() as db:
            college_ids = (await db.execute(select(College.college_id))).scalars().all()

            window_start = datetime.now(timezone.utc) - timedelta(days=ACTIVE_WINDOW_DAYS)
            active_students_rows = await db.execute(
                select(Message.college_id, func.count(distinct(Message.student_id)))
                .where(Message.created_at >= window_start)
                .group_by(Message.college_id)
            )
            active_students_by_college = dict(active_students_rows.all())

            documents_indexed_rows = await db.execute(
                select(Document.college_id, func.count())
                .where(Document.document_status == "success")
                .group_by(Document.college_id)
            )
            documents_indexed_by_college = dict(documents_indexed_rows.all())

            # Set every college explicitly (including zero), not just the
            # ones with a non-zero count - otherwise a college whose active
            # students drop to zero, or whose last document gets deleted,
            # would keep showing its last nonzero value in Grafana forever
            # instead of the gauge actually reflecting the current state.
            for college_id in college_ids:
                ACTIVE_STUDENTS_7D.labels(college_id=str(college_id)).set(active_students_by_college.get(college_id, 0))
                DOCUMENTS_INDEXED.labels(college_id=str(college_id)).set(documents_indexed_by_college.get(college_id, 0))
    except Exception as e:
        logger.error(f"Failed to refresh product health gauges: {e}", extra={"extra_data": {"error": str(e)}})
