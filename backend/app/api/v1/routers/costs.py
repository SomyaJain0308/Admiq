"""
Internal cost-analytics endpoints - per-student/per-session unit economics
built on top of the cost_events table (backend/app/models/CostEvent.py,
populated by backend/app/services/cost_service.py).

DELIBERATELY separate from every college-staff-facing router:
- gated by X-Cost-Reporting-Token (settings.cost_reporting_token), NOT
  verify_college_access - a college staff member's JWT cannot reach this
  no matter what, by construction.
- NOT registered anywhere in the frontend (no hook, no dashboard card).
This is your internal margin data. If you ever want a customer-facing
usage view, build a separate, deliberately-limited endpoint for that -
don't loosen this one or point the existing dashboard at it.
"""

import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.config import get_settings
from backend.app.database import get_db
from backend.app.models.CostEvent import CostEvent
from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
from backend.app.models.Message import Message
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession
from backend.app.schemas.costs import CostByStage, CostByType, CostStatsResponse, TopCostStudent

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/costs", tags=["Internal Cost Reporting"])

TRAILING_WINDOW_DAYS = 7
TOP_STUDENTS_LIMIT = 10
TOP_STAGES_LIMIT = 10


def _verify_token(x_cost_reporting_token: str | None) -> None:
    settings = get_settings()
    if not settings.cost_reporting_token:
        # Fail closed: if no token is configured, refuse everything rather
        # than silently running unprotected - same policy as
        # internal_tasks.py's _verify_token.
        raise HTTPException(status_code=503, detail="cost_reporting_token not configured")
    if x_cost_reporting_token != settings.cost_reporting_token:
        raise HTTPException(status_code=401, detail="Invalid or missing X-Cost-Reporting-Token")


@router.get("/{college_id}/stats", response_model=CostStatsResponse)
async def get_cost_stats(
    college_id: int,
    db: AsyncSession = Depends(get_db),
    x_cost_reporting_token: str | None = Header(default=None),
):
    _verify_token(x_cost_reporting_token)

    now = datetime.utcnow()
    week_start = now - timedelta(days=TRAILING_WINDOW_DAYS)
    prev_week_start = now - timedelta(days=2 * TRAILING_WINDOW_DAYS)

    # ---------------- Totals & trend ----------------

    total_all_time, total_last_7_days, total_prev_7_days = (
        await db.execute(
            select(
                func.coalesce(func.sum(CostEvent.cost_usd), 0),
                func.coalesce(func.sum(case((CostEvent.created_at >= week_start, CostEvent.cost_usd), else_=0)), 0),
                func.coalesce(func.sum(case((and_(CostEvent.created_at >= prev_week_start, CostEvent.created_at < week_start), CostEvent.cost_usd), else_=0)), 0),
            ).where(CostEvent.college_id == college_id)
        )
    ).one()

    # ---------------- Per-student unit economics ----------------
    # LEFT JOIN so every student in the college counts, including ones with
    # $0 in cost_events (never engaged, or engaged before tracking existed) -
    # that's the honest denominator for "what does a student cost us",
    # not just the subset who happened to trigger a cost event.
    per_student_cost = (
        select(Student.student_id, Student.student_name, func.coalesce(func.sum(CostEvent.cost_usd), 0).label("total_cost"))
        .select_from(Student)
        .outerjoin(CostEvent, and_(CostEvent.college_id == Student.college_id, CostEvent.student_id == Student.student_id))
        .where(Student.college_id == college_id)
        .group_by(Student.student_id, Student.student_name)
        .subquery()
    )
    total_students, avg_cost_per_student, median_cost_per_student, p95_cost_per_student = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.avg(per_student_cost.c.total_cost), 0),
                func.coalesce(func.percentile_cont(0.5).within_group(per_student_cost.c.total_cost), 0),
                func.coalesce(func.percentile_cont(0.95).within_group(per_student_cost.c.total_cost), 0),
            ).select_from(per_student_cost)
        )
    ).one()

    top_students_rows = (
        await db.execute(select(per_student_cost.c.student_id, per_student_cost.c.student_name, per_student_cost.c.total_cost).order_by(per_student_cost.c.total_cost.desc()).limit(TOP_STUDENTS_LIMIT))
    ).all()
    top_students_by_cost = [TopCostStudent(student_id=student_id, student_name=student_name, total_cost_usd=float(total_cost)) for student_id, student_name, total_cost in top_students_rows]

    # ---------------- Per-session unit economics ----------------

    per_session_cost = (
        select(StudentSession.session_id, func.coalesce(func.sum(CostEvent.cost_usd), 0).label("total_cost"))
        .select_from(StudentSession)
        .outerjoin(CostEvent, and_(CostEvent.college_id == StudentSession.college_id, CostEvent.session_id == StudentSession.session_id))
        .where(StudentSession.college_id == college_id)
        .group_by(StudentSession.session_id)
        .subquery()
    )
    total_sessions, avg_cost_per_session, median_cost_per_session = (
        await db.execute(
            select(
                func.count(),
                func.coalesce(func.avg(per_session_cost.c.total_cost), 0),
                func.coalesce(func.percentile_cont(0.5).within_group(per_session_cost.c.total_cost), 0),
            ).select_from(per_session_cost)
        )
    ).one()

    # ---------------- Breakdowns ----------------

    cost_by_type_rows = (await db.execute(select(CostEvent.cost_type, func.sum(CostEvent.cost_usd)).where(CostEvent.college_id == college_id).group_by(CostEvent.cost_type))).all()
    total_for_pct = float(total_all_time) or 1.0  # avoid divide-by-zero when a college has no cost events yet
    cost_by_type = [CostByType(cost_type=cost_type, total_cost_usd=float(cost), percent_of_total=float(cost) / total_for_pct * 100) for cost_type, cost in cost_by_type_rows]

    cost_by_stage_rows = (
        await db.execute(
            select(CostEvent.stage, func.sum(CostEvent.cost_usd), func.sum(CostEvent.input_tokens + CostEvent.output_tokens))
            .where(CostEvent.college_id == college_id, CostEvent.stage.isnot(None))
            .group_by(CostEvent.stage)
            .order_by(func.sum(CostEvent.cost_usd).desc())
            .limit(TOP_STAGES_LIMIT)
        )
    ).all()
    cost_by_stage = [CostByStage(stage=stage, total_cost_usd=float(cost), total_tokens=int(tokens or 0)) for stage, cost, tokens in cost_by_stage_rows]

    # ---------------- Efficiency: escalated vs self-served sessions ----------------
    # A session "escalated" if the specific message that got flagged
    # (LowConfidenceQuery.question_message_id) belongs to it - joined
    # through Message rather than just "any session belonging to a student
    # who was ever escalated", so a student's earlier clean sessions don't
    # get miscounted as escalated just because a later one was.
    escalated_session_ids = (
        select(Message.session_id)
        .select_from(LowConfidenceQuery)
        .join(Message, and_(Message.college_id == LowConfidenceQuery.college_id, Message.message_id == LowConfidenceQuery.question_message_id))
        .where(LowConfidenceQuery.college_id == college_id, Message.session_id.isnot(None))
        .distinct()
        .subquery()
    )
    sessions_with_escalation = (await db.execute(select(func.count()).select_from(escalated_session_ids))).scalar_one()

    avg_escalated, avg_non_escalated = (
        await db.execute(
            select(
                func.avg(case((per_session_cost.c.session_id.in_(select(escalated_session_ids.c.session_id)), per_session_cost.c.total_cost), else_=None)),
                func.avg(case((per_session_cost.c.session_id.notin_(select(escalated_session_ids.c.session_id)), per_session_cost.c.total_cost), else_=None)),
            ).select_from(per_session_cost)
        )
    ).one()

    return CostStatsResponse(
        total_cost_usd_all_time=float(total_all_time),
        total_cost_usd_last_7_days=float(total_last_7_days),
        total_cost_usd_prev_7_days=float(total_prev_7_days),
        total_students=total_students or 0,
        avg_cost_per_student_usd=float(avg_cost_per_student),
        median_cost_per_student_usd=float(median_cost_per_student),
        p95_cost_per_student_usd=float(p95_cost_per_student),
        top_students_by_cost=top_students_by_cost,
        total_sessions=total_sessions or 0,
        avg_cost_per_session_usd=float(avg_cost_per_session),
        median_cost_per_session_usd=float(median_cost_per_session),
        cost_by_type=cost_by_type,
        cost_by_stage=cost_by_stage,
        sessions_with_low_confidence_escalation=sessions_with_escalation or 0,
        avg_cost_per_escalated_session_usd=float(avg_escalated) if avg_escalated is not None else None,
        avg_cost_per_non_escalated_session_usd=float(avg_non_escalated) if avg_non_escalated is not None else None,
    )
