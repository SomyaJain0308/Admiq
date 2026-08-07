from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.models import LowConfidenceQuery, Message
from backend.app.schemas.low_confidence import LowConfidenceResponse


router = APIRouter(tags=["low_confidence"])

@router.get("/router/low_confidence/{college_id}", response_model=list[LowConfidenceResponse])
async def get_low_confidence_queries(college_id: int, db: AsyncSession = Depends(get_db)):
    low_confidence_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved == False))
    low_confidence_queries = low_confidence_result.scalars().all()
    if not low_confidence_queries:
        raise HTTPException(status_code=404, detail="No queries need human handoff at this time.")

    responses = []
    for query in low_confidence_queries:
        question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
        question_content = question_content_result.scalars().first()
        answer_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.answer_message_id).limit(1))
        answer_content = answer_content_result.scalars().first()

        responses.append(LowConfidenceResponse(
            query_id=query.query_id,
            college_id=query.college_id,
            student_id=query.student_id,
            question_message_id=query.question_message_id,
            question_content=question_content,
            answer_message_id=query.answer_message_id,
            answer_content=answer_content,
            resolved=query.resolved,
            resolved_at=query.resolved_at if query.resolved_at else None
        ))
    return responses



@router.get("/router/low_confidence/{college_id}/query/{query_id}", response_model=LowConfidenceResponse)
async def get_low_confidence_query(college_id: int, query_id: int, db: AsyncSession = Depends(get_db)):
    existing_query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id).limit(1))
    existing_query = existing_query_result.scalars().first()
    if not existing_query:
        raise HTTPException(status_code=404, detail="Low confidence query not found")
    return existing_query
