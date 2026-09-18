from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.Student import Student
    from backend.app.models.College import College
    from backend.app.models.Message import Message
from backend.app.database import Base

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class StudentSession(Base):
    __tablename__ = "student_sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    session_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    session_summary: Mapped[str | None] = mapped_column(Text)
    profile_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    reengagement_nudge_sent: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    total_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    # Generic guided-flow state (e.g. the eligibility checker) that should
    # take over routing from the free-chat RAG agent while it's set. Kept
    # generic ({"flow": "eligibility_check", "step": ..., ...}) rather than a
    # one-off "eligibility_state" column so future scripted flows (e.g. the
    # admission-procedure walkthrough) can reuse the same mechanism. NULL
    # means the student is in ordinary free-chat with the agent.
    active_flow: Mapped[dict | None] = mapped_column(JSONB)


    student: Mapped["Student"] = relationship(back_populates="sessions", overlaps="sessions")
    college: Mapped["College"] = relationship(back_populates="sessions", overlaps="sessions,student")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", overlaps="messages,messages")

    __table_args__ = (
        CheckConstraint("session_status IN ('active', 'closed')"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        UniqueConstraint("college_id", "session_id"),
        Index("one_active_session_per_student", "college_id", "student_id", unique=True, postgresql_where=(session_status == "active")),
        Index("ix_sessions_college_id_student_id_session_status", "college_id", "student_id", "session_status"), 
        Index("ix_sessions_last_message_at", "last_message_at"), 
    )