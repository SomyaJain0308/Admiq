from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.Chunk import Chunk
from backend.app.database import Base

from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class KnowledgeConflict(Base):
    """One row per (new chunk, existing chunk) pair that conflict detection
    (see backend/app/rag/conflict_detection.py) judged to state a different,
    incompatible fact for the same specific thing (a fee, a deadline, an
    eligibility rule, ...). Raised whenever a chunk enters or changes -
    document ingestion, a staff reply to a flagged query, or a proactive/
    edited knowledge-base entry - never blocks that write; it only surfaces
    the pair on the Conflicts page for a human to resolve. Both chunk FKs
    cascade so a conflict disappears on its own once either side is deleted."""

    __tablename__ = "knowledge_conflicts"

    conflict_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    new_chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    existing_chunk_id: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_distance: Mapped[float | None] = mapped_column(Numeric(5, 4))
    explanation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="open")
    resolved_by: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship("College", viewonly=True)
    new_chunk: Mapped["Chunk"] = relationship("Chunk", primaryjoin=("and_(KnowledgeConflict.college_id == Chunk.college_id, " "KnowledgeConflict.new_chunk_id == Chunk.chunk_id)"), foreign_keys="[KnowledgeConflict.college_id, KnowledgeConflict.new_chunk_id]", viewonly=True)
    existing_chunk: Mapped["Chunk"] = relationship("Chunk", primaryjoin=("and_(KnowledgeConflict.college_id == Chunk.college_id, " "KnowledgeConflict.existing_chunk_id == Chunk.chunk_id)"), foreign_keys="[KnowledgeConflict.college_id, KnowledgeConflict.existing_chunk_id]", viewonly=True)

    __table_args__ = (
        CheckConstraint("status IN ('open', 'resolved', 'dismissed')", name="knowledge_conflicts_status_check"),
        UniqueConstraint("college_id", "conflict_id"),
        # Same new/existing chunk pair shouldn't get flagged twice.
        UniqueConstraint("college_id", "new_chunk_id", "existing_chunk_id"),
        ForeignKeyConstraint(["college_id", "new_chunk_id"], ["chunks.college_id", "chunks.chunk_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "existing_chunk_id"], ["chunks.college_id", "chunks.chunk_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "resolved_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"]),
        Index("ix_knowledge_conflicts_college_status_created_at", "college_id", "status", "created_at"),
        Index("ix_knowledge_conflicts_new_chunk_id", "new_chunk_id"),
        Index("ix_knowledge_conflicts_existing_chunk_id", "existing_chunk_id"),
    )
