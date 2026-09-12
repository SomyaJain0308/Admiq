"""
Periodic Celery task that refreshes the three cost gauges from
monitoring/cost_metrics.py: COST_USD_ALL_TIME, COST_USD_LAST_7D and
COST_USD_BY_TYPE_LAST_7D. Same reasoning as product_health_tasks.py: these
are Gauges (a current snapshot recomputed from cost_events), not Counters,
and every college + cost_type gets set explicitly on every run - including
zero - so a college that stops incurring cost shows a real drop in Grafana
instead of its Prometheus series just going stale at the last nonzero value.

Reads straight from cost_events - the same table backend/app/api/v1/routers
/costs.py aggregates for its token-gated endpoint - but that endpoint isn't
touched or called here. This is a separate, read-only query path that only
ever feeds Prometheus.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal
from backend.app.models.College import College
from backend.app.models.CostEvent import CostEvent
from backend.app.monitoring.cost_metrics import COST_USD_ALL_TIME, COST_USD_LAST_7D, COST_USD_BY_TYPE_LAST_7D

logger = logging.getLogger(__name__)

COST_WINDOW_DAYS = 7
COST_TYPES = ("llm", "embedding", "whatsapp")  # must match CostEvent.cost_type's CheckConstraint


@celery_app.task
def refresh_cost_gauges_task():
    asyncio.run(_refresh_cost_gauges_async())


async def _refresh_cost_gauges_async():
    try:
        async with AsyncSessionLocal() as db:
            college_ids = (await db.execute(select(College.college_id))).scalars().all()
            window_start = datetime.now(timezone.utc) - timedelta(days=COST_WINDOW_DAYS)

            all_time_rows = await db.execute(select(CostEvent.college_id, func.coalesce(func.sum(CostEvent.cost_usd), 0)).group_by(CostEvent.college_id))
            all_time_by_college = dict(all_time_rows.all())

            last_7d_rows = await db.execute(select(CostEvent.college_id, func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(CostEvent.created_at >= window_start).group_by(CostEvent.college_id))
            last_7d_by_college = dict(last_7d_rows.all())

            by_type_rows = await db.execute(select(CostEvent.college_id, CostEvent.cost_type, func.coalesce(func.sum(CostEvent.cost_usd), 0)).where(CostEvent.created_at >= window_start).group_by(CostEvent.college_id, CostEvent.cost_type))
            by_type_by_college = {(college_id, cost_type): total for college_id, cost_type, total in by_type_rows.all()}

            for college_id in college_ids:
                COST_USD_ALL_TIME.labels(college_id=str(college_id)).set(float(all_time_by_college.get(college_id, 0)))
                COST_USD_LAST_7D.labels(college_id=str(college_id)).set(float(last_7d_by_college.get(college_id, 0)))
                for cost_type in COST_TYPES:
                    COST_USD_BY_TYPE_LAST_7D.labels(college_id=str(college_id), cost_type=cost_type).set(float(by_type_by_college.get((college_id, cost_type), 0)))
    except Exception as e:
        logger.error(f"Failed to refresh cost gauges: {e}", extra={"extra_data": {"error": str(e)}})
