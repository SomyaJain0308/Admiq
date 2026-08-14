import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import func, select

from backend.app.background_tasks.celery_app import celery_app
from backend.app.database import AsyncSessionLocal, engine
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.services.lead_scoring import compute_lead_score


logger = logging.getLogger(__name__)

BATCH_SIZE = 200


@celery_app.task
def recompute_lead_scores_task():
    asyncio.run(_recompute_lead_scores_async())


async def _recompute_lead_scores_async():
    try:
        async with AsyncSessionLocal() as db:
            try:
                offset = 0
                total_updated = 0
                while True:
                    students_result = await db.execute(select(Student).order_by(Student.student_id).offset(offset).limit(BATCH_SIZE))
                    students = students_result.scalars().all()
                    if not students:
                        break
                    for student in students:
                        try:
                            stats_result = await db.execute(
                                select(func.count(), func.max(StudentSession.last_message_at)).select_from(StudentSession).where(
                                    StudentSession.college_id == student.college_id,
                                    StudentSession.student_id == student.student_id,
                                )
                            )
                            total_sessions, last_activity = stats_result.one()
                            days_since_last_activity = None
                            if last_activity is not None:
                                now = datetime.now(timezone.utc)
                                if last_activity.tzinfo is None:
                                    last_activity = last_activity.replace(tzinfo=timezone.utc)
                                days_since_last_activity = (now - last_activity).total_seconds() / 86400
                            profile_signals = student.profile_signals or {}
                            student.lead_score = compute_lead_score(
                                interest_signal_history=student.interest_signal_history,
                                days_since_last_activity=days_since_last_activity,
                                total_sessions=total_sessions or 0,
                                concerns=profile_signals.get("concerns"),
                                competing_colleges=profile_signals.get("competing_colleges"),
                                dropoff_reason=profile_signals.get("dropoff_reason"),
                            )
                            student.lead_score_updated_at = datetime.now(timezone.utc)
                            total_updated += 1
                        except Exception as e:
                            logger.error(f"Error recomputing lead score for student {student.student_id}: {e}", exc_info=True)
                            continue
                    await db.commit()
                    offset += BATCH_SIZE
                logger.info(f"Recomputed lead scores for {total_updated} students.")
            finally:
                await db.close()
    finally:
        await engine.dispose()