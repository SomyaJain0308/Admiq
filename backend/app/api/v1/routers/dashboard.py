from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.database import get_db
from backend.app.models.Chunk import Chunk
from backend.app.models.CollegeStaff_StaffCollege import CollegeStaff
from backend.app.models.Document import Document
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Message import Message
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.schemas.dashboard import CourseInterestCount, DailyMessageCount, DashboardStatsResponse, StaffResolutionCount
from backend.app.services.auth_services import verify_college_access

router = APIRouter(tags=["dashboard"], prefix="/router/dashboard")

# Matches the "Hot" band cutoff in the frontend's lib/leadScore.js - kept in
# sync manually since there's no shared source of truth between the two
# codebases for this constant.
HOT_LEAD_THRESHOLD = 70

# Trailing 7 days rather than a calendar week - simpler to reason about (no
# "which day does the week start on" question) and avoids a Monday morning
# where "this week" would otherwise mean "the last few hours".
TRAILING_WINDOW_DAYS = 7


@router.get("/{college_id}/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    college_id: int,
    db: AsyncSession = Depends(get_db),
    membership: CollegeStaff = Depends(verify_college_access),
):
    now = datetime.utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=TRAILING_WINDOW_DAYS)
    prev_week_start = now - timedelta(days=2 * TRAILING_WINDOW_DAYS)

    # ---------------- Queue / staff SLA ----------------

    # extract('epoch', ...) turns the interval into a plain number of
    # seconds so avg()/percentile_cont() can operate on it directly.
    resolution_seconds_expr = func.extract("epoch", LowConfidenceQuery.resolved_at - LowConfidenceQuery.flagged_at)
    resolution_stats = (
        await db.execute(
            select(
                func.avg(resolution_seconds_expr),
                func.percentile_cont(0.5).within_group(resolution_seconds_expr),
            ).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved.is_(True))
        )
    ).one()
    avg_resolution_seconds, median_resolution_seconds = resolution_stats

    resolved_today, resolved_last_7_days = (
        await db.execute(
            select(
                func.sum(case((LowConfidenceQuery.resolved_at >= today_start, 1), else_=0)),
                func.sum(case((LowConfidenceQuery.resolved_at >= week_start, 1), else_=0)),
            ).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved.is_(True))
        )
    ).one()

    oldest_open_flagged_at = (
        await db.execute(select(func.min(LowConfidenceQuery.flagged_at)).where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved.is_(False)))
    ).scalar_one()
    oldest_open_query_age_seconds = (now - oldest_open_flagged_at).total_seconds() if oldest_open_flagged_at else None

    # Who's actually clearing the queue, not just how many are cleared -
    # inner join to CollegeStaff means an unresolved (resolved_by IS NULL)
    # row can never appear here, so no extra resolved filter needed beyond
    # what's already required to have a resolved_by at all.
    resolutions_by_staff_rows = (
        await db.execute(
            select(CollegeStaff.staff_id, CollegeStaff.staff_name, func.count(LowConfidenceQuery.query_id))
            .select_from(LowConfidenceQuery)
            .join(CollegeStaff, CollegeStaff.staff_id == LowConfidenceQuery.resolved_by)
            .where(LowConfidenceQuery.college_id == college_id, LowConfidenceQuery.resolved_at >= week_start)
            .group_by(CollegeStaff.staff_id, CollegeStaff.staff_name)
            .order_by(func.count(LowConfidenceQuery.query_id).desc())
            .limit(10)
        )
    ).all()
    resolutions_by_staff = [StaffResolutionCount(staff_id=staff_id, staff_name=staff_name, resolved_count=count) for staff_id, staff_name, count in resolutions_by_staff_rows]

    # ---------------- Lead funnel ----------------

    new_students_today, new_students_last_7_days, new_students_prev_7_days = (
        await db.execute(
            select(
                func.sum(case((Student.created_at >= today_start, 1), else_=0)),
                func.sum(case((Student.created_at >= week_start, 1), else_=0)),
                func.sum(case((and_(Student.created_at >= prev_week_start, Student.created_at < week_start), 1), else_=0)),
            ).where(Student.college_id == college_id)
        )
    ).one()

    newly_hot_leads_last_7_days, unassigned_hot_leads = (
        await db.execute(
            select(
                func.sum(case((and_(Student.lead_score >= HOT_LEAD_THRESHOLD, Student.lead_score_updated_at >= week_start), 1), else_=0)),
                func.sum(case((and_(Student.lead_score >= HOT_LEAD_THRESHOLD, Student.assigned_to.is_(None)), 1), else_=0)),
            ).where(Student.college_id == college_id)
        )
    ).one()

    course_interest_rows = (
        await db.execute(
            select(Student.course_interest, func.count())
            .where(Student.college_id == college_id, Student.course_interest.isnot(None), Student.course_interest != "")
            .group_by(Student.course_interest)
            .order_by(func.count().desc())
            .limit(8)
        )
    ).all()
    course_interest_breakdown = [CourseInterestCount(course_interest=course_interest, count=count) for course_interest, count in course_interest_rows]

    # ---------------- Conversation volume & engagement ----------------

    # date_trunc buckets every message into the UTC day it was sent, so a
    # single grouped query gets the whole trailing series at once instead of
    # one query per day.
    series_start = today_start - timedelta(days=TRAILING_WINDOW_DAYS - 1)
    daily_message_rows = (
        await db.execute(
            select(func.date_trunc("day", Message.created_at), func.count())
            .where(Message.college_id == college_id, Message.created_at >= series_start)
            .group_by(func.date_trunc("day", Message.created_at))
            .order_by(func.date_trunc("day", Message.created_at))
        )
    ).all()
    counts_by_day = {day.date(): count for day, count in daily_message_rows}
    # Zero-fill days with no activity so the frontend gets a fixed-length,
    # gap-free series to plot rather than having to fill gaps itself.
    messages_last_7_days = [
        DailyMessageCount(date=series_start.date() + timedelta(days=offset), count=counts_by_day.get(series_start.date() + timedelta(days=offset), 0))
        for offset in range(TRAILING_WINDOW_DAYS)
    ]
    messages_today = counts_by_day.get(today_start.date(), 0)

    active_sessions = (
        await db.execute(select(func.count()).select_from(StudentSession).where(StudentSession.college_id == college_id, StudentSession.session_status == "active"))
    ).scalar_one()

    # A session "bounces" if it never gets past a couple of messages - a
    # proxy for the student losing interest (or the bot losing them)
    # almost immediately. Computed from actual message counts per session
    # rather than trusting any session-level counter, since none exists.
    session_message_counts = (
        select(Message.session_id, func.count().label("msg_count")).where(Message.college_id == college_id, Message.session_id.isnot(None)).group_by(Message.session_id)
    ).subquery()
    total_sessions_with_messages, bounced_sessions = (
        await db.execute(select(func.count(), func.sum(case((session_message_counts.c.msg_count <= 2, 1), else_=0))).select_from(session_message_counts))
    ).one()
    bounce_rate_pct = (bounced_sessions or 0) / total_sessions_with_messages * 100 if total_sessions_with_messages else None

    # ---------------- Knowledge base / bot health ----------------
    # (thumbs-up/down feedback is intentionally out of scope here - tracked
    # as its own metric elsewhere)

    total_assistant_messages, total_flagged_queries = (
        await db.execute(
            select(
                select(func.count()).select_from(Message).where(Message.college_id == college_id, Message.messager_role == "assistant").scalar_subquery(),
                select(func.count()).select_from(LowConfidenceQuery).where(LowConfidenceQuery.college_id == college_id).scalar_subquery(),
            )
        )
    ).one()
    self_serve_rate_pct = (total_assistant_messages - total_flagged_queries) / total_assistant_messages * 100 if total_assistant_messages else None

    failed_documents, avg_document_quality_score = (
        await db.execute(
            select(
                func.sum(case((Document.document_status == "failed", 1), else_=0)),
                func.avg(case((Document.document_status == "success", Document.quality_score), else_=None)),
            ).where(Document.college_id == college_id)
        )
    ).one()

    # Every successful queue reply (and every save-as-answer direct
    # message) adds exactly one staff_answer chunk tied to the resolved
    # query that produced it - joining through that link lets this be
    # windowed by when the chunk was actually added, even though Chunk
    # itself has no created_at column of its own.
    staff_answers_added_last_7_days = (
        await db.execute(
            select(func.count())
            .select_from(Chunk)
            .join(LowConfidenceQuery, and_(LowConfidenceQuery.college_id == Chunk.college_id, LowConfidenceQuery.query_id == Chunk.source_query_id))
            .where(Chunk.college_id == college_id, Chunk.source_type == "staff_answer", LowConfidenceQuery.resolved_at >= week_start)
        )
    ).scalar_one()

    return DashboardStatsResponse(
        avg_resolution_seconds=float(avg_resolution_seconds) if avg_resolution_seconds is not None else None,
        median_resolution_seconds=float(median_resolution_seconds) if median_resolution_seconds is not None else None,
        resolved_today=resolved_today or 0,
        resolved_last_7_days=resolved_last_7_days or 0,
        oldest_open_query_age_seconds=oldest_open_query_age_seconds,
        resolutions_by_staff_last_7_days=resolutions_by_staff,
        new_students_today=new_students_today or 0,
        new_students_last_7_days=new_students_last_7_days or 0,
        new_students_prev_7_days=new_students_prev_7_days or 0,
        newly_hot_leads_last_7_days=newly_hot_leads_last_7_days or 0,
        unassigned_hot_leads=unassigned_hot_leads or 0,
        course_interest_breakdown=course_interest_breakdown,
        messages_today=messages_today,
        messages_last_7_days=messages_last_7_days,
        active_sessions=active_sessions,
        bounce_rate_pct=bounce_rate_pct,
        self_serve_rate_pct=self_serve_rate_pct,
        failed_documents=failed_documents or 0,
        avg_document_quality_score=float(avg_document_quality_score) if avg_document_quality_score is not None else None,
        staff_answers_added_last_7_days=staff_answers_added_last_7_days or 0,
    )
