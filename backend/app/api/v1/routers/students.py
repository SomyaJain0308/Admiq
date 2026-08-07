from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.app.database import get_db
from backend.app.models.Message import Message

router = APIRouter()


@router.get("/view_convo/{college_id}/{student_id}")
async def view_conversation(college_id: int, student_id: int, db: AsyncSession = Depends(get_db)):
    convo_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == student_id).order_by(Message.created_at.asc()))
    convo = convo_result.scalars().all()
    if not convo:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return convo