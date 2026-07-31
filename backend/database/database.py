from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

from backend.rag.config import get_settings

settings = get_settings()

engine = create_async_engine(settings.database_url)

AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, autocommit=False, autoflush=False, expire_on_commit=False)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as db:
        yield db