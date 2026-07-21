from sqlalchemy import select, func

from backend.database import models

def get_or_create_active_session(db, college_id, student_id) -> models.StudentSession:
    existing_session = db.execute(select(models.StudentSession).where(models.StudentSession.college_id == college_id, models.StudentSession.student_id == student_id, models.StudentSession.session_status == "active")).scalars().first()
    
    if existing_session is not None:
        existing_session.last_message_at = func.now()
        db.commit()
        db.refresh(existing_session)
        return existing_session
    
    new_student_session = models.StudentSession(college_id=college_id, student_id=student_id, session_status="active", last_message_at=func.now())
    db.add(new_student_session)
    db.commit()
    db.refresh(new_student_session)
    return new_student_session



def update_session_summary(db, session, session_summary: str):
    session.session_summary = session_summary
    session.last_message_at = func.now()
    db.commit()
    db.refresh(session)
    return session