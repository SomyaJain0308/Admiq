from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.Message import Message
    from backend.app.models.CollegeStaff_StaffCollege import StaffCollege
    from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
    from backend.app.models.StudentSession import StudentSession
from backend.app.database import Base

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_phone: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    student_name: Mapped[str | None] = mapped_column(Text)
    course_interest: Mapped[str | None] = mapped_column(Text)
    academic_scores: Mapped[dict | None] = mapped_column(JSONB)  # e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary: Mapped[str | None] = mapped_column(Text)
    assigned_to: Mapped[int | None] = mapped_column(Integer)
    internal_notes: Mapped[str | None] = mapped_column(Text)  # manual staff notes, separate from AI-generated summary
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("college_id", "student_id"),
        UniqueConstraint("college_id", "whatsapp_user_id"),
        UniqueConstraint("college_id", "student_phone"),
        CheckConstraint("student_status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested')", name="students_student_status_check"), # Add more later if required
        Index("ix_students_college_id", "college_id"),
        Index("ix_students_college_id_student_status", "college_id", "student_status"),
        ForeignKeyConstraint(["college_id", "assigned_to"], ["staff_colleges.college_id", "staff_colleges.staff_id"])
    )

    college: Mapped["College"] = relationship(back_populates="students")
    messages: Mapped[list["Message"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="messages")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="low_confidence_queries")
    assigned_staff_membership: Mapped["StaffCollege | None"] = relationship("StaffCollege", primaryjoin=("and_(Student.college_id == StaffCollege.college_id, " "Student.assigned_to == StaffCollege.staff_id)"), foreign_keys="[Student.college_id, Student.assigned_to]", viewonly=True)
    sessions: Mapped[list["StudentSession"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="sessions")
