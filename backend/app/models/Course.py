from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.EligibilityRule import EligibilityRule
from backend.app.database import Base

from sqlalchemy import Boolean, ForeignKey, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Course(Base):
    """
    A course/program a college offers, configured by staff so the WhatsApp
    eligibility-checker flow (see services/eligibility_service.py) has
    something structured to select from and evaluate against - deliberately
    separate from the free-text Document/RAG knowledge base, since eligibility
    is a pass/fail decision that shouldn't be left to an LLM inferring from a
    brochure chunk.
    """
    __tablename__ = "courses"

    course_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    # Self-reference: lets a "programme type" (e.g. "B.Tech") group several
    # branches (e.g. "Computer Science", "Civil") under it, so a college
    # with dozens of courses doesn't need to cram them into one flat,
    # 10-row-capped WhatsApp list - see services/eligibility_service.py.
    # NULL = a normal top-level course/programme type; set = this row is a
    # branch of another course. ON DELETE SET NULL, not CASCADE: deleting a
    # programme type orphans its branches back to the top level rather than
    # deleting them too.
    parent_course_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("courses.course_id", ondelete="SET NULL"), nullable=True)
    course_name: Mapped[str] = mapped_column(Text, nullable=False)
    # Draft courses are never offered to students in the WhatsApp course list -
    # lets staff build/edit a course's rules without it going live mid-edit.
    is_published: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Reserved for the admission-procedure flow (explicitly not being built
    # yet) so that feature doesn't need a schema migration later.
    admission_procedure: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="courses")
    eligibility_rules: Mapped[list["EligibilityRule"]] = relationship(back_populates="course", cascade="all, delete-orphan", order_by="EligibilityRule.order_index")
    # No cascade="delete-orphan" here to match the DB's ON DELETE SET NULL:
    # deleting a parent should orphan its children (parent_course_id ->
    # NULL), not delete them.
    parent: Mapped["Course | None"] = relationship("Course", remote_side="Course.course_id", back_populates="children")
    children: Mapped[list["Course"]] = relationship("Course", back_populates="parent", order_by="Course.order_index")

    __table_args__ = (
        UniqueConstraint("college_id", "course_id"),
        Index("ix_courses_college_id", "college_id"),
        Index("ix_courses_parent_course_id", "parent_course_id"),
    )
