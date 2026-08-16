from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.Message import Message
    from backend.app.models.CollegeStaff_StaffCollege import StaffCollege
    from backend.app.models.Student import Student
from backend.app.database import Base


from sqlalchemy import Boolean, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class LowConfidenceQuery(Base):
    __tablename__ = "low_confidence_queries"

    query_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    resolved_by: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    flagged_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="low_confidence_queries", overlaps="low_confidence_queries")
    student: Mapped["Student"] = relationship(back_populates="low_confidence_queries", overlaps="college,low_confidence_queries")
    question_message: Mapped["Message"] = relationship("Message", primaryjoin=("and_(LowConfidenceQuery.college_id == Message.college_id, " "LowConfidenceQuery.question_message_id == Message.message_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.question_message_id]", viewonly=True)
    answer_message: Mapped["Message"] = relationship("Message", primaryjoin=("and_(LowConfidenceQuery.college_id == Message.college_id, " "LowConfidenceQuery.answer_message_id == Message.message_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.answer_message_id]", viewonly=True)
    resolved_by_membership: Mapped["StaffCollege | None"] = relationship("StaffCollege", primaryjoin=("and_(LowConfidenceQuery.college_id == StaffCollege.college_id, " "LowConfidenceQuery.resolved_by == StaffCollege.staff_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.resolved_by]", viewonly=True,)
    
    __table_args__ = (
        UniqueConstraint("college_id", "query_id"),
        UniqueConstraint("college_id", "answer_message_id"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "question_message_id"], ["messages.college_id", "messages.message_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "answer_message_id"], ["messages.college_id", "messages.message_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "resolved_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"],),
        Index("ix_low_confidence_queries_college_id_resolved", "college_id", "resolved"),
        Index("ix_low_confidence_queries_student_id", "student_id"),
    )