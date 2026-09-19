from datetime import datetime
from backend.app.database import Base

from sqlalchemy import ForeignKeyConstraint, Index, Integer, Text, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column


class EligibilityRuleHistory(Base):
    """
    Append-only snapshot of an EligibilityRule taken every time staff PATCH
    it (config and/or is_active), written by the router right after the
    commit - see api/v1/routers/eligibility.py's update_rule. Answers "when
    did this cutoff change, and to what" directly from analytics instead of
    having to ask the college, which eligibility_events alone can't do (it
    only knows about the student-facing flow, not staff edits).

    Not a foreign key to eligibility_rules on rule_id in a way that cascades
    away history - rows here deliberately outlive the rule itself (a
    deleted rule's history is still worth keeping around to explain a
    pass-rate shift after the fact), so there's no ON DELETE CASCADE here.
    college_id/course_id are still kept as plain columns (no FK) for the
    same reason: a deleted course shouldn't take its rule-change history
    down with it either.
    """
    __tablename__ = "eligibility_rule_history"

    history_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    # Full post-change snapshot (not a diff) - simplest thing that's still
    # enough to answer "what did the cutoff used to be", and matches
    # config's own shape so it can go through describe_rule unchanged if
    # ever needed for a human-readable history view.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    is_active: Mapped[bool] = mapped_column(nullable=False)
    # Which staff member made the change - nullable since a change could in
    # principle come from a non-staff-authenticated path (a script, a
    # future admin API key) rather than every write having to be a real
    # college_staff row.
    changed_by_staff_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        ForeignKeyConstraint(["changed_by_staff_id"], ["college_staff.staff_id"], ondelete="SET NULL"),
        Index("ix_eligibility_rule_history_college_id_rule_id", "college_id", "rule_id"),
        Index("ix_eligibility_rule_history_college_id_created_at", "college_id", "created_at"),
    )
