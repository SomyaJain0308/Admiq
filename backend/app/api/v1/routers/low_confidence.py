from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from datetime import datetime


from backend.app.services.auth_services import verify_college_access
from backend.app.monitoring.logging_utils import get_logger
from backend.app.monitoring.low_confidence import LOW_CONFIDENCE_QUERIES_OPEN, LOW_CONFIDENCE_RESOLUTION_TIME_SECONDS, LOW_CONFIDENCE_QUERIES_RESOLVED
from backend.app.config import get_settings
from backend.app.services.whatsapp_service import send_whatsapp_text_message
from backend.app.database import get_db
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Message import Message
from backend.app.models.Student import Student
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.models.Chunk import Chunk
from backend.app.schemas.low_confidence import LowConfidenceResponse
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.rag.staff_reply_context import reconstruct_staff_answer
from backend.app.services.tenant_service import save_staff_message

logger = get_logger()

router = APIRouter(tags=["low_confidence"])

@router.get("/router/low_confidence/{college_id}", response_model=list[LowConfidenceResponse])
async def get_low_confidence_queries(college_id: int, resolved: bool = False, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    low_confidence_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved == resolved))
    low_confidence_queries = low_confidence_result.scalars().all()
    if not resolved:
        LOW_CONFIDENCE_QUERIES_OPEN.set(len(low_confidence_queries))
    if not low_confidence_queries:
        raise HTTPException(status_code=404, detail="No queries found.")

    responses = []
    for query in low_confidence_queries:
        question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
        question_content = question_content_result.scalars().first()
        answer_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.answer_message_id).limit(1))
        answer_content = answer_content_result.scalars().first()
        responses.append(LowConfidenceResponse(query_id=query.query_id, college_id=query.college_id, student_id=query.student_id, question_message_id=query.question_message_id, question_content=question_content, answer_message_id=query.answer_message_id, answer_content=answer_content, resolved=query.resolved, resolved_at=query.resolved_at if query.resolved_at else None, resolved_by=query.resolved_by if query.resolved_by else None, flagged_at=query.flagged_at))
    return responses



@router.get("/router/low_confidence/{college_id}/query/{query_id}", response_model=LowConfidenceResponse)
async def get_low_confidence_query(college_id: int, query_id: int, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id).limit(1))
    query = query_result.scalars().first()
    if not query:
        raise HTTPException(status_code=404, detail="Low confidence query not found")
    question_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.question_message_id).limit(1))
    question_content = question_content_result.scalars().first()
    answer_content_result = await db.execute(select(Message.content).where(Message.college_id == college_id, Message.message_id == query.answer_message_id).limit(1))
    answer_content = answer_content_result.scalars().first()
    return LowConfidenceResponse(query_id=query.query_id, college_id=query.college_id, student_id=query.student_id, question_message_id=query.question_message_id, question_content=question_content, answer_message_id=query.answer_message_id, answer_content=answer_content, resolved=query.resolved, resolved_at=query.resolved_at if query.resolved_at else None, resolved_by=query.resolved_by if query.resolved_by else None, flagged_at=query.flagged_at)



@router.post("/router/low_confidence/{college_id}/query/{query_id}/reply")
async def reply_to_low_confidence_query(college_id: int, query_id: int, reply_message: str, expires_at: datetime, db: AsyncSession = Depends(get_db), membership: CollegeStaff = Depends(verify_college_access)):
    staff_id = membership.staff_id
    settings = get_settings()
    query_result = await db.execute(select(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.query_id == query_id, LowConfidenceQuery.resolved == False).limit(1))
    query = query_result.scalars().first()
    if query is None:
        raise HTTPException(status_code=404, detail="Low Confidence Query not found")
    # Get last 4 message of the chat and get the question and answer from llm to store in db
    original_question_result = await db.execute(select(Message).where(Message.college_id ==college_id, Message.message_id == query.question_message_id).limit(1))
    original_question = original_question_result.scalars().first()
    context_result = await db.execute(select(Message).where(Message.college_id == college_id, Message.student_id == query.student_id, Message.created_at <= original_question.created_at).order_by(Message.created_at.desc()).limit(4))
    recent_messages = list(reversed(context_result.scalars().all())) # If you sorted ASC and took LIMIT 4 instead, you'd get the 4 oldest messages in that student's entire history, not the 4 closest to this question — wrong messages entirely. So DESC is required for correctness of which rows come back. But DESC also means the rows arrive in the wrong order for feeding to an LLM as a conversation — you'd get [newest, ..., oldest]
    recent_conversation = "\n".join(f"{m.messager_role}: {m.content}" for m in recent_messages)
    reconstructed = reconstruct_staff_answer(recent_conversation, reply_message)
    # save + send the staff reply as a real message
    student_result = await db.execute(select(Student).where(Student.college_id == college_id, Student.student_id == query.student_id).limit(1))
    student = student_result.scalars().first()
    staff_message = await save_staff_message(db, college_id=college_id, student_id=query.student_id, staff_id=staff_id, content=reply_message, session_id=original_question.session_id)

    whatsapp_number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == college_id).limit(1))
    whatsapp_number = whatsapp_number_result.scalars().first()
    send_result = await send_whatsapp_text_message(phone_number_id=whatsapp_number.phone_number_id, to=student.whatsapp_user_id, message=reply_message, access_token=settings.whatsapp_access_token)
    if not send_result["ok"]:
        logger.error(f"Failed to deliver staff reply to student_id={query.student_id}")
    # Embed + Store as a retrievable chunk
    embedder = GoogleGenerativeAIEmbeddings(model=settings.embedding_model, api_key=settings.gemini_api_key, output_dimensionality=settings.vector_size)
    chunk_text = f"Question: {reconstructed.question}\nAnswer: {reconstructed.answer}"
    vector = embedder.embed_query(chunk_text)
    db.add(Chunk(college_id=college_id, chunk_content=chunk_text, embedding=vector, chunk_index=0, source_type="staff_answer", source_query_id=query_id, expires_at=expires_at))
    query.resolved = True
    query.resolved_by = staff_id
    query.resolved_at = datetime.utcnow()
    LOW_CONFIDENCE_QUERIES_RESOLVED.inc()
    LOW_CONFIDENCE_RESOLUTION_TIME_SECONDS.observe((query.resolved_at - query.flagged_at).total_seconds())
    await db.commit()

    return {"status": "resolved", "reconstructed_question": reconstructed.question, "expires_at": expires_at}
    
    