import logging
import asyncio
from datetime import datetime, timezone

from backend.app.monitoring.background_tasks_metrics import BACKGROUND_TASK_BATCH_DURATION, BACKGROUND_TASK_BATCH_SIZE, BACKGROUND_TASK_ITEM_OUTCOMES, LEAD_SCORE_DISTRIBUTION
from sqlalchemy import select, func

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal, engine
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.rag.student_profile import generate_profile_update
from backend.app.services.lead_scoring import compute_lead_score

logger = logging.getLogger(__name__)

BATCH_SIZE = 50
INTEREST_SIGNAL_HISTORY_CAP = 5


@celery_app.task
def process_closed_sessions_task():
    asyncio.run(_process_closed_sessions_async())


async def _process_closed_sessions_async():
    try:
        async with AsyncSessionLocal() as db:
            try:
                with BACKGROUND_TASK_BATCH_DURATION.labels(task_name="update_student_profile").time():
                    closed_sessions_result = await db.execute(select(StudentSession).where(StudentSession.session_status == "closed", StudentSession.profile_processed == False).limit(BATCH_SIZE))
                    closed_sessions = closed_sessions_result.scalars().all()
                    BACKGROUND_TASK_BATCH_SIZE.labels(task_name="update_student_profile").observe(len(closed_sessions))
                    if not closed_sessions:
                        return
                    processed_count = 0
                    for session in closed_sessions:
                        try:
                            if not session.session_summary:
                                session.profile_processed = True
                                BACKGROUND_TASK_ITEM_OUTCOMES.labels(task_name="update_student_profile", outcome="no_session_summary").inc()
                                continue
                            student_result = await db.execute(select(Student).where(Student.college_id == session.college_id, Student.student_id == session.student_id).limit(1))
                            student = student_result.scalars().first()
                            if not student:
                                logger.warning(f"Student not found for session {session.session_id}. Skipping profile merge.")
                                session.profile_processed = True
                                BACKGROUND_TASK_ITEM_OUTCOMES.labels(task_name="update_student_profile", outcome="no_student_session").inc()
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
                            interest_history = list(student.interest_signal_history or [])
                            interest_history.append(updated_profile.interest_signal)
                            student.interest_signal_history = interest_history[-INTEREST_SIGNAL_HISTORY_CAP:]
                            total_sessions_result = await db.execute(select(func.count()).select_from(StudentSession).where(StudentSession.college_id == student.college_id, StudentSession.student_id == student.student_id))
                            total_sessions = total_sessions_result.scalars().first()
                            last_activity = session.last_message_at or session.started_at
                            days_since_last_activity = None
                            if last_activity is not None:
                                now = datetime.now(timezone.utc).replace(tzinfo=None)
                                if last_activity.tzinfo is not None:
                                    last_activity = last_activity.astimezone(timezone.utc).replace(tzinfo=None)
                                days_since_last_activity = (now - last_activity).total_seconds() / 86400
                            student.lead_score = compute_lead_score(interest_signal_history=student.interest_signal_history, days_since_last_activity=days_since_last_activity, total_sessions=total_sessions, concerns=student.profile_signals.get("concerns"), competing_colleges=student.profile_signals.get("competing_colleges"), dropoff_reason=student.profile_signals.get("dropoff_reason"))
                            LEAD_SCORE_DISTRIBUTION.labels(source="session_close").observe(student.lead_score)
                            student.lead_score_updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
                            session.profile_processed = True
                            processed_count += 1
                            BACKGROUND_TASK_ITEM_OUTCOMES.labels(task_name="update_student_profile", outcome="student_profle_updated").inc()
                        except Exception as e:
                            logger.error(f"Error processing session {session.session_id}: {e}", exc_info=True)
                            BACKGROUND_TASK_ITEM_OUTCOMES.labels(task_name="update_student_profile", outcome="error").inc()
                            continue
                    await db.commit()
                    logger.info(f"Processed {processed_count}/{len(closed_sessions)} closed sessions into student profiles.")
            finally:
                await db.close()
    finally:
        await engine.dispose()