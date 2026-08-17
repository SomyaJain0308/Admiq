from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest, multiprocess, CollectorRegistry

from backend.app.monitoring.logging_utils import METRICS_CONTENT_TYPE


router = APIRouter(tags=["Metrics"])


@router.get("/router/metrics")
async def prometheus_metrics():
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return PlainTextResponse(generate_latest(registry), media_type=METRICS_CONTENT_TYPE)