from backend.app.models import models
from fastapi import HTTPException, status
from sqlalchemy import select

async def resolve_college_from_phone_number_id(db, phone_number_id) -> int:
    # query whatsapp_numbers where phone_number_id = webhook metadata.phone_number_id if not found -> reject webhook / log unknown tenant return college_id
    result = await db.execute(select(models.WhatsAppNumber).where(models.WhatsAppNumber.phone_number_id == phone_number_id))
    whatsapp_number = result.scalars().first()
    if whatsapp_number is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="College not found with this WhatsApp Number (Unknown Tenant)")
    
    return whatsapp_number.college_id



async def get_or_create_student(db, college_id, student_phone, whatsapp_user_id, student_name=None) -> models.Student:
    # find student by college_id + whatsapp_user_id if not found, maybe fallback college_id + student_phone if found, update name if existing name is None, create student
    result = await db.execute(select(models.Student).where(models.Student.college_id == college_id, models.Student.whatsapp_user_id == whatsapp_user_id))
    student = result.scalars().first()
    if student is not None:
        if student.student_name is None and student_name is not None:
            student.student_name = student_name
            await db.commit()
            await db.refresh(student)
        return student
    
    result = await db.execute(select(models.Student).where(models.Student.college_id == college_id, models.Student.student_phone == student_phone))
    student = result.scalars().first()
    if student is not None:
        if student.student_name is None and student_name is not None:
            student.student_name = student_name
            await db.commit()
            await db.refresh(student)
        return student
    
    new_student = models.Student(
        college_id=college_id,
        whatsapp_user_id=whatsapp_user_id,
        student_phone=student_phone,
        student_name=student_name
    )

    db.add(new_student)
    await db.commit()
    await db.refresh(new_student)
    return new_student



async def save_inbound_message(db, college_id, student_id, whatsapp_message_id, content, whatsapp_timestamp, message_type, raw_payload, session_id: int | None = None) -> models.Message:
    result = await db.execute(select(models.Message).where(models.Message.college_id == college_id, models.Message.whatsapp_message_id == whatsapp_message_id))
    message = result.scalars().first()
    if message is not None:
        return message
    
    new_message = models.Message(
        college_id=college_id,
        student_id=student_id,
        session_id=session_id,
        messager_role="student",
        whatsapp_message_id=whatsapp_message_id,
        content=content,
        whatsapp_timestamp=whatsapp_timestamp,
        message_type=message_type,
        raw_payload=raw_payload
    )

    db.add(new_message)
    await db.commit()
    await db.refresh(new_message)
    return new_message
  


async def save_assistant_message(db, college_id: int, student_id: int, content: str, sources: list[str] | None = None, session_id: int | None = None) -> models.Message:
    message = models.Message(
        college_id=college_id,
        student_id=student_id,
        session_id=session_id,
        messager_role="assistant",
        content=content,
        sources={"sources": sources or []},
        message_type="text",
    )
    db.add(message)
    await db.commit()
    await db.refresh(message)
    return message


async def flag_low_confidence_query(db, college_id, student_id, question_message_id, answer_message_id, similarity_score):
    entry = models.LowConfidenceQuery(college_id=college_id, student_id=student_id, question_message_id=question_message_id, answer_message_id=answer_message_id, similarity_score=similarity_score)
    db.add(entry)
    await db.commit()
    return entry