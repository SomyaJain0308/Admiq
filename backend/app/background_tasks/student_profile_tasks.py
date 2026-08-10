import logging
import asyncio

from sqlalchemy import select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.rag.student_profile import generate_profile_update


logger = logging.getLogger(__name__)

BATCH_SIZE = 50


@celery_app.task
async def _process_closed_sessions_async():
    async with AsyncSessionLocal() as db:
        try:
            closed_sessions_result = await db.execute(select(StudentSession).where(StudentSession.session_status == "closed", StudentSession.profile_processed == False).limit(BATCH_SIZE))
            closed_sessions = closed_sessions_result.scalars().all()
            if not closed_sessions:
                return
            processed_count = 0
            for session in closed_sessions:
                try:
                    if not session.session_summary:
                        session.profile_processed = True
                        continue
                    student_result = await db.execute(select(Student).where(Student.college_id == session.college_id, Student.student_id == session.student_id).limit(1))
                    student = student_result.scalars().first()
                    if not student:
                        logger.warning(f"Student not found for session {session.session_id}. Skipping profile merge.")
                        session.profile_processed = True
                        continue
                    updated_profile = await generate_profile_update(existing_summary=student.summary, session_summary=session.session_summary, existing_profile_signals=student.profile_signals)
                    student.summary = updated_profile.summary
                    if updated_profile.course_interest:
                        student.course_interest = updated_profile.course_interest
                    if updated_profile.academic_score_updates:
                        merged_scores = dict(student.academic_scores or {})
                        merged_scores.update(updated_profile.academic_score_updates)
                        student.academic_scores = merged_scores
                    existing_profile_signals = student.profile_signals or {}
                    student.profile_signals = {"concerns": updated_profile.concerns, "guardian_involvement": updated_profile.guardian_involvement if updated_profile.guardian_involvement is not None else existing_profile_signals.get("guardian_involvement"), "competing_colleges": updated_profile.competing_colleges, "dropoff_reason": updated_profile.dropoff_reason}
                    session.profile_processed = True
                    processed_count += 1
                except Exception as e:
                    logger.error(f"Error processing session {session.session_id}: {e}", exc_info=True)
                    continue
            await db.commit()
            logger.info(f"Processed {processed_count}/{len(closed_sessions)} closed sessions into student profiles.")
        finally:
            await db.close()