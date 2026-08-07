from datetime import datetime

from backend.app.database import Base
from backend.app.models.College import College
from backend.app.models.Student import Student
from backend.app.models.StudentSession import StudentSession

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    messager_role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSONB)
    feedback: Mapped[bool | None] = mapped_column(Boolean)  # FALSE = 👎 (store in low_confidence_queries)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    whatsapp_message_id: Mapped[str | None] = mapped_column(Text)
    whatsapp_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    message_type: Mapped[str] = mapped_column(Text, server_default="text", nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    session_id: Mapped[int | None] = mapped_column(Integer)

    student: Mapped["Student"] = relationship(back_populates="messages", overlaps="messages,messages")
    college: Mapped["College"] = relationship(back_populates="messages", overlaps="messages,messages,student")
    session: Mapped["StudentSession"] = relationship(back_populates="messages", overlaps="college,messages,messages,student")


    __table_args__ = (
        CheckConstraint("messager_role IN ('student', 'assistant')", name="messages_messager_role_check"), 
        CheckConstraint("feedback IS NULL OR messager_role = 'assistant'", name="messages_feedback_assistant_check"),
        Index("ix_messages_student_id_created_at", "student_id", "created_at"), 
        Index("ix_messages_college_id_created_at", "college_id", "created_at"),
        Index("ix_messages_college_id_session_id", "college_id", "session_id"), 
        UniqueConstraint("college_id", "whatsapp_message_id"),
        UniqueConstraint("college_id", "message_id"),
        ForeignKeyConstraint(["college_id", "session_id"], ["student_sessions.college_id", "student_sessions.session_id"]),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
    )
