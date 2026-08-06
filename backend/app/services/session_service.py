from sqlalchemy import select, func

from backend.app.models import models



async def get_or_create_active_session(db, college_id, student_id) -> models.StudentSession:
    result = await db.execute(select(models.StudentSession).where(models.StudentSession.college_id == college_id, models.StudentSession.student_id == student_id, models.StudentSession.session_status == "active"))
    existing_session = result.scalars().first()
    
    if existing_session is not None:
        existing_session.last_message_at = func.now()
        await db.commit()
        await db.refresh(existing_session)
        return existing_session
    
    new_student_session = models.StudentSession(college_id=college_id, student_id=student_id, session_status="active", last_message_at=func.now())
    db.add(new_student_session)
    await db.commit()
    await db.refresh(new_student_session)
    return new_student_session


async def update_session_summary(db, session, session_summary: str):
    session.session_summary = session_summary
    session.last_message_at = func.now()
    await db.commit()
    await db.refresh(session)
    return session


def is_session_budget_exceeded(session, max_tokens: int) -> bool:
    return session.total_tokens_used >= max_tokens


async def record_session_tokens(db, session, input_tokens: int, output_tokens: int):
    session.total_tokens_used += (input_tokens + output_tokens)
    session.last_message_at = func.now()
    await db.commit()
    await db.refresh(session)
    return session