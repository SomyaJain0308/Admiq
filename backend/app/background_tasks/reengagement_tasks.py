import asyncio
import logging
from datetime import datetime, timedelta, timezone
from sqlalchemy import select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.config import get_settings
from backend.app.database import AsyncSessionLocal, engine
from backend.app.models.College import College
from backend.app.models.Message import Message
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.models.WhatsappNumber import WhatsAppNumber
from backend.app.rag.reengagement import generate_reengagement_message
from backend.app.services.whatsapp_service import send_whatsapp_text_message



logger = logging.getLogger(__name__)

BATCH_SIZE = 50

REENGAGEMENT_WINDOW_START_HOURS = 23.0
REENGAGEMENT_WINDOW_END_HOURS = 23.6

MIN_LEAD_SCORE_FOR_NUDGE = 15



@celery_app.task
def check_and_send_reengagement_nudges_task():
    asyncio.run(_check_and_send_reenagegement_nudges_async())


async def _check_and_send_reenagegement_nudges_async():
    try:
        async with AsyncSessionLocal() as db:
            try:
                now = datetime.now(timezone.utc)
                window_start = now - timedelta(hours=REENGAGEMENT_WINDOW_END_HOURS)
                window_end = now - timedelta(hours=REENGAGEMENT_WINDOW_START_HOURS)
                candidates_result = await db.execute(select(StudentSession).where(StudentSession.last_message_at >= window_start, StudentSession.last_message_at <= window_end, StudentSession.reengagement_nudge_sent == False).limit(BATCH_SIZE))
                candidate_sessions = candidates_result.scalars().all()
                if not candidate_sessions:
                    return
                sent_count = 0
                for session in candidate_sessions:
                    try:
                        latest_session_result = await db.execute(select(StudentSession.session_id).where(StudentSession.college_id == session.college_id, StudentSession.student_id == session.student_id).order_by(StudentSession.last_message_at.desc()).limit(1))
                        latest_session_id = latest_session_result.scalars().first()
                        if latest_session_id != session.session_id:
                            session.reengagement_nudge_sent = True
                            continue
                        if not session.session_summary:
                            continue
                        student_result = await db.execute(select(Student).where(Student.college_id == session.college_id, Student.student_id == session.student_id).limit(1))
                        student = student_result.scalars().first()
                        if not student:
                            session.reengagement_nudge_sent = True
                            continue
                        interest_history = student.interest_signal_history or []
                        if interest_history and interest_history[-1] == "negative":
                            session.reengagement_nudge_sent = True
                            continue
                        if student.lead_score < MIN_LEAD_SCORE_FOR_NUDGE:
                            session.reengagement_nudge_sent = True
                            continue
                        college_result = await db.execute(select(College).where(College.college_id == student.college_id).limit(1))
                        college = college_result.scalars().first()
                        profile_signals = student.profile_signals or {}
                        nudge = await generate_reengagement_message(student_summary=student.summary, session_summary=session.session_summary, concerns=profile_signals.get("concerns"), course_interest=student.course_interest, key_strengths=college.key_strengths if college else None)
                        if not nudge.should_send or not nudge.message:
                            session.reengagement_nudge_sent = True
                            continue
                        number_result = await db.execute(select(WhatsAppNumber).where(WhatsAppNumber.college_id == student.college_id).limit(1))
                        whatsapp_number = number_result.scalars().first()
                        if not whatsapp_number:
                            logger.warning(f"No Whatsapp number configured for college {student.college_id}. Skipping nudge for student  {student.student_id}.")
                            continue
                        send_result  = await send_whatsapp_text_message(phone_number_id=whatsapp_number.phone_number_id, to=student.whatsapp_user_id, message=nudge.message, access_token=get_settings().whatsapp_access_token)
                        if send_result["ok"]:
                            db.add(Message(college_id=student.college_id, student_id=student.student_id, session_id=session.session_id, messager_role="assistant", content=nudge.message, message_type="reengagement_nudge"))
                            session.reengagement_nudge_sent = True
                            sent_count += 1
                        else:
                            logger.error(f"Failed to send reengagement nudge to student {student.student_id}: {send_result}")
                    except Exception as e:
                        logger.error(f"Error processing reengagement candidate session {session.session_id}: {e}", exc_info=True)
                        continue
                await db.commit()
                logger.info(f"Sent {sent_count}/{len(candidate_sessions)} reengagement nudges.")
            finally:
                await db.close()
    finally:
        await engine.dispose()