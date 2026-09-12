from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from starlette.requests import Request

from backend.app.config import get_settings
from backend.app.monitoring.api_metrics import DB_QUERY_ERRORS

settings = get_settings()

# For async parts of my codebase
engine = create_async_engine(settings.database_url)
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False)

# For sync parts of my codebase (mainly celery_tasks.py)
SYNC_DATABASE_URL = settings.database_url.replace("+asyncpg", "")
sync_engine = create_engine(SYNC_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=sync_engine)

class Base(DeclarativeBase):
    pass

# Must come after Base is defined - this import triggers models/__init__.py, which imports every model class so SQLAlchemy's registry is fully populated before any mapper configuration runs (see comment in models/__init__.py).
from backend.app import models

async def get_db(request: Request = None):
    # request is optional so get_db still works for any non-HTTP caller
    # (there isn't one today, but nothing here should require FastAPI's
    # dependency injection to work) - when it's present (the normal case,
    # injected automatically by FastAPI) it just gives DB_QUERY_ERRORS a
    # route label to distinguish which endpoint's query failed.
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except SQLAlchemyError as e:
            operation = request.url.path if request is not None else "unknown"
            DB_QUERY_ERRORS.labels(operation=operation, error_type=type(e).__name__).inc()
            raise