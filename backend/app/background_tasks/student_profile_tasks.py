import logging
from sqlalchemy import select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import SessionLocal
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.rag.student_profile import merge_student_profile


logger = logging.getLogger(__name__)

BATCH_SIZE = 50


@celery_app.task
def process_closed_sessions_task():
    db = SessionLocal()
    try:
        closed_sessions = db.execute(select(StudentSession).where(StudentSession.session_status == "closed", StudentSession.profile_processed == False).limit(BATCH_SIZE)).scalars().all()
        if not closed_sessions:
            return
        processed_count = 0
        for session in closed_sessions:
            try:
                if not session.session_summary:
                    session.profile_processed = True
                    continue
                student = db.execute(select(Student).where(Student.college_id == session.college_id, Student.student_id == session.student_id).limit(1)).scalars().first()
                if not student:
                    logger.warning(f"Student not found for session {session.session_id}. Skipping profile merge.")
                    session.profile_processed = True
                    continue
                merged_summary = merge_student_profile(existing_summary=student.summary, session_summary=session.session_summary)
                student.summary = merged_summary
                session.profile_processed = True
                processed_count += 1
            except Exception as e:
                logger.error(f"Error processing session {session.session_id}: {e}", exc_info=True)
                continue
        db.commit()
        logger.info(f"Processed {processed_count}/{len(closed_sessions)} closed sessions into student profiles.")
    finally:
        db.close()