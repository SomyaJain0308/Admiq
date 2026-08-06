from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.database import get_db


router = APIRouter(tags=["Health Check"])

@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    # Perform a simple database query to check connectivity
    try:
        await db.execute(select(1))
    except Exception:
        raise HTTPException(status_code=503, detail="Database connection failed, Service Unavailable")

    return {"status": "healthy"}