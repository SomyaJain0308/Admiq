from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi_limiter import FastAPILimiter
import redis.asyncio as redis
import os


from backend.app.config import get_settings
from backend.app.rag.security import SecurityPipeline
from backend.app.monitoring.logging_utils import get_logger
from backend.app.rag.agent import Agent
from backend.app.api.v1.routers.internal_tasks import router as internal_tasks_router
from backend.app.api.v1.routers.whatsapp_chat import router as whatsapp_router
from backend.app.api.v1.routers.metrics import router as metrics_router
from backend.app.api.v1.routers.colleges import router as colleges_router
from backend.app.api.v1.routers.staff import router as staff_router
from backend.app.api.v1.routers.test_chat import router as chat_router
from backend.app.api.v1.routers.health_check import router as health_router
from backend.app.api.v1.routers.low_confidence import router as low_confidence_router
from backend.app.api.v1.routers.students import router as students_router
from backend.app.api.v1.routers.documents import router as documents_router



load_dotenv()

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI): # Initialize all components on startup
    app.state.security = SecurityPipeline()
    app.state.agent = Agent()

    settings = get_settings()

    redis_connection = redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)
    await FastAPILimiter.init(redis_connection)

    logger.info('Starting Production API...', extra={'extra_data': {"environment": settings.app_env, "primary_model": settings.primary_model, "tracing_enabled": settings.langchain_tracing_v2}})
    logger.info("All components initialized. Ready to serve requests.")

    yield

    await FastAPILimiter.close()
    logger.info("Shutting down...")


app = FastAPI(title="Admiq", description="A college admission chatbot.", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://admiq-v1.vercel.app",
        "http://localhost:5173",  # local frontend dev server
    ],
    allow_methods=["*"],
    allow_headers=["*"],
    # Needed so the frontend's downloadFile() can read the server's suggested
    # filename for CSV exports - browsers don't expose this header across
    # origins by default even though the response includes it.
    expose_headers=["Content-Disposition"],
)


app.include_router(documents_router)
app.include_router(whatsapp_router)
app.include_router(internal_tasks_router)
app.include_router(metrics_router)
app.include_router(colleges_router)
app.include_router(staff_router)
app.include_router(chat_router)
app.include_router(health_router)
app.include_router(low_confidence_router)
app.include_router(students_router)