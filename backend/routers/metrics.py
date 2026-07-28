from fastapi import APIRouter
from fastapi.responses import PlainTextResponse
from prometheus_client import generate_latest

from backend.rag.monitoring import METRICS_CONTENT_TYPE


router = APIRouter(tags=["Metrics"])


@router.get("/router/metrics")
async def prometheus_metrics():
    return PlainTextResponse(generate_latest(), media_type=METRICS_CONTENT_TYPE)