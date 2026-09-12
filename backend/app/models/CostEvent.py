from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.Student import Student
    from backend.app.models.StudentSession import StudentSession
    from backend.app.models.Document import Document
from backend.app.database import Base

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, Text, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CostEvent(Base):
    """One row per billable unit of work (an LLM call, an embedding batch, or
    a WhatsApp send). See backend/app/services/cost_service.py for how these
    get created and backend/app/api/v1/routers/costs.py for the aggregation
    queries (median/avg/p95 per student, per college) built on top of this
    table. student_id/session_id/document_id are nullable - a cost isn't
    always attributable to one student (e.g. document ingestion embeddings)."""

    __tablename__ = "cost_events"

    cost_event_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int | None] = mapped_column(Integer)
    session_id: Mapped[int | None] = mapped_column(Integer)
    document_id: Mapped[int | None] = mapped_column(Integer)
    cost_type: Mapped[str] = mapped_column(Text, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float] = mapped_column(Numeric(12, 6), nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship("College", viewonly=True)
    student: Mapped["Student | None"] = relationship("Student", primaryjoin=("and_(CostEvent.college_id == Student.college_id, " "CostEvent.student_id == Student.student_id)"), foreign_keys="[CostEvent.college_id, CostEvent.student_id]", viewonly=True)
    session: Mapped["StudentSession | None"] = relationship("StudentSession", primaryjoin=("and_(CostEvent.college_id == StudentSession.college_id, " "CostEvent.session_id == StudentSession.session_id)"), foreign_keys="[CostEvent.college_id, CostEvent.session_id]", viewonly=True)
    document: Mapped["Document | None"] = relationship("Document", primaryjoin=("and_(CostEvent.college_id == Document.college_id, " "CostEvent.document_id == Document.document_id)"), foreign_keys="[CostEvent.college_id, CostEvent.document_id]", viewonly=True)

    __table_args__ = (
        CheckConstraint("cost_type IN ('llm', 'embedding', 'whatsapp')", name="cost_events_cost_type_check"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "session_id"], ["student_sessions.college_id", "student_sessions.session_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "document_id"], ["documents.college_id", "documents.document_id"], ondelete="CASCADE"),
        Index("ix_cost_events_college_id_student_id", "college_id", "student_id"),
        Index("ix_cost_events_college_id_created_at", "college_id", "created_at"),
        Index("ix_cost_events_student_id_created_at", "student_id", "created_at"),
        Index("ix_cost_events_cost_type", "cost_type"),
    )
