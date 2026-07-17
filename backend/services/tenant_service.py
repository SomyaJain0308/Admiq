from backend.database import models
from backend.schemas.whatsapp import InboundWhatsAppMessage
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import select

def resolve_college_from_phone_number_id(db, phone_number_id) -> int:
    # query whatsapp_numbers where phone_number_id = webhook metadata.phone_number_id if not found -> reject webhook / log unknown tenant return college_id
    whatsapp_number = db.execute(select(models.WhatsAppNumber).where(models.WhatsAppNumber.phone_number_id == phone_number_id)).scalars().first()
    
    if whatsapp_number is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="College not found with this WhatsApp Number (Unknown Tenant)")
    
    return whatsapp_number.college_id



def get_or_create_student(db, college_id, student_phone, whatsapp_user_id, student_name=None) -> models.Student:
    # find student by college_id + whatsapp_user_id if not found, maybe fallback college_id + student_phone if found, update name if existing name is None, create student
    student = db.execute(select(models.Student).where(models.Student.college_id == college_id, models.Student.whatsapp_user_id == whatsapp_user_id,)).scalars().first()
    
    if student is not None:

        if student.student_name is None and student_name is not None:
            student.student_name = student_name

            db.commit()
            db.refresh(student)

        return student
    
    student = db.execute(select(models.Student).where(models.Student.college_id == college_id, models.Student.student_phone == student_phone,)).scalars().first()
    
    if student is not None:

        if student.student_name is None and student_name is not None:
            student.student_name = student_name

            db.commit()
            db.refresh(student)

        return student
    
    new_student = models.Student(
        college_id=college_id,
        whatsapp_user_id=whatsapp_user_id,
        student_phone=student_phone,
        student_name=student_name
    )

    db.add(new_student)
    db.commit()
    db.refresh(new_student)

    return new_student



def save_inbound_message(db, college_id, student_id, whatsapp_message_id, content, whatsapp_timestamp, message_type, raw_payload) -> models.Message:
    message = db.execute(select(models.Message).where(models.Message.college_id == college_id, models.Message.whatsapp_message_id == whatsapp_message_id)).scalars().first()

    if message is not None:
        return message
    
    new_message = models.Message(
        college_id=college_id,
        student_id=student_id,
        messager_role="student",
        whatsapp_message_id=whatsapp_message_id,
        content=content,
        whatsapp_timestamp=whatsapp_timestamp,
        message_type=message_type,
        raw_payload=raw_payload
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return new_message



def extract_whatsapp_message_events(payload) -> list[InboundWhatsAppMessage]:
    value = payload["entry"][0]["changes"][0]["value"]
    messages = value.get("messages", [])
    if not messages:
        return []

    if payload["entry"][0]["changes"][0]["value"]["messages"][0]["type"] != "text":
        return []

    event = InboundWhatsAppMessage(
    whatsapp_business_account_id = payload["entry"][0]["id"],
    phone_number_id = value["metadata"]["phone_number_id"],
    display_phone_number = value["metadata"]["display_phone_number"],
    
    whatsapp_user_id = value["contacts"][0]["wa_id"],
    student_name = value["contacts"][0]["profile"]["name"],
    student_phone = value["messages"][0]["from"],
    whatsapp_message_id = value["messages"][0]["id"],
    whatsapp_timestamp = datetime.fromtimestamp(int(value["messages"][0]["timestamp"]), tz=timezone.utc,),
    message_type = value["messages"][0]["type"],
    content = value["messages"][0]["text"]["body"],
    
    raw_payload = payload,
    )
    
    return [event]    

def save_assistant_message(db, college_id: int, student_id: int, content: str, sources: list[str] | None = None) -> models.Message:
    message = models.Message(
        college_id=college_id,
        student_id=student_id,
        messager_role="assistant",
        content=content,
        sources={"sources": sources or []},
        message_type="text",
    )

    db.add(message)
    db.commit()
    db.refresh(message)

    return message