from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.Course import Course
    from backend.app.models.Student import Student
from backend.app.database import Base

from sqlalchemy import CheckConstraint, ForeignKeyConstraint, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

# Every step name the WhatsApp eligibility flow's state machine uses (see
# services/eligibility_service.py's module docstring) - kept in sync with
# that file's step names, not with EligibilityRule.rule_type.
FLOW_STEPS = ("await_start_confirm", "await_course", "await_category", "await_summary_confirm", "await_rule", "await_procedure_interest", "await_another_course")

# 'passed'/'failed'/'borderline' only ever occur with step='await_rule' (the
# only step with a pass/fail verdict); 'cancelled'/'timed_out' can happen at
# any step - that's exactly the "where do students drop off" question this
# table exists to answer.
OUTCOMES = ("passed", "failed", "borderline", "cancelled", "timed_out")


class EligibilityEvent(Base):
    """
    One row per exit from the WhatsApp eligibility-checker flow - a rule
    verdict (passed/failed/borderline) or a drop-off (cancelled/timed_out) -
    written by services/eligibility_service.py's _record_eligibility_event.
    Powers the "pass/fail rate per course" and "where do students drop off"
    admin analytics (see api/v1/routers/eligibility.py's /analytics
    endpoint) that Student.profile_signals alone can't answer: that field
    only keeps each student's own last 10 checks, has no drop-off entries at
    all (cancel/timeout never touch it), and can't be aggregated cheaply
    across every student in a college.

    rule_index is the rule's 0-based position in its course's ordered rule
    list *at the time of the event* (same numbering "Question X of Y" shows
    a student) - not a foreign key to eligibility_rules, so a later reorder,
    edit, or delete of that rule doesn't retroactively corrupt historical
    events. NULL for any step other than await_rule.
    """

    __tablename__ = "eligibility_events"

    event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int | None] = mapped_column(Integer)
    step: Mapped[str] = mapped_column(Text, nullable=False)
    rule_index: Mapped[int | None] = mapped_column(Integer)
    outcome: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    student: Mapped["Student"] = relationship("Student", primaryjoin=("and_(EligibilityEvent.college_id == Student.college_id, " "EligibilityEvent.student_id == Student.student_id)"), foreign_keys="[EligibilityEvent.college_id, EligibilityEvent.student_id]", viewonly=True)
    course: Mapped["Course | None"] = relationship("Course", primaryjoin=("and_(EligibilityEvent.college_id == Course.college_id, " "EligibilityEvent.course_id == Course.course_id)"), foreign_keys="[EligibilityEvent.college_id, EligibilityEvent.course_id]", viewonly=True)

    __table_args__ = (
        CheckConstraint("step IN ('await_start_confirm','await_course','await_category','await_summary_confirm','await_rule','await_procedure_interest','await_another_course')", name="eligibility_events_step_check"),
        CheckConstraint("outcome IN ('passed','failed','borderline','cancelled','timed_out')", name="eligibility_events_outcome_check"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "course_id"], ["courses.college_id", "courses.course_id"], ondelete="SET NULL"),
        Index("ix_eligibility_events_college_id_course_id", "college_id", "course_id"),
        Index("ix_eligibility_events_college_id_outcome", "college_id", "outcome"),
        Index("ix_eligibility_events_college_id_created_at", "college_id", "created_at"),
    )
