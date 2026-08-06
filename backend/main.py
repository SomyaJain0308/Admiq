from contextlib import asynccontextmanager
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings
from backend.rag.security import SecurityPipeline
from backend.rag.monitoring import get_logger, MetricsCollector
from backend.rag.agent import ProductionAgent
from backend.routers.documents import router as documents_router
from backend.routers.whatsappChat import router as whatsapp_router
from backend.routers.metrics import router as metrics_router
from backend.routers.colleges import router as colleges_router
from backend.routers.staff import router as staff_router
from backend.routers.testChat import router as chat_router
from backend.routers.healthCheck import router as health_router



load_dotenv()

logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI): # Initialize all components on startup
    app.state.security = SecurityPipeline()
    app.state.metrics = MetricsCollector()
    app.state.agent = ProductionAgent()

    settings = get_settings()

    logger.info('Starting Production API...', extra={'extra_data': {"environment": settings.app_env, "primary_model": settings.primary_model, "tracing_enabled": settings.langchain_tracing_v2}})
    logger.info("All components initialized. Ready to serve requests.")

    yield

    logger.info("Shutting down...", extra={"extra_data": app.state.metrics.summary})


app = FastAPI(title="Admiq", description="A college admission chatbot.", version="1.0.0", lifespan=lifespan)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]) # NOTE: change allow_origins in production.

app.include_router(documents_router)
app.include_router(whatsapp_router)
app.include_router(metrics_router)
app.include_router(colleges_router)
app.include_router(staff_router)
app.include_router(chat_router)
app.include_router(health_router)