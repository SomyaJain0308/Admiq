from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy import create_engine

from backend.app.config import get_settings

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

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db