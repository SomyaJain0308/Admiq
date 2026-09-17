from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.CollegeStaff_StaffCollege import StaffCollege
from backend.app.database import Base


from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    num_pages: Mapped[int | None] = mapped_column(Integer)
    document_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="processing")
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int] = mapped_column(Integer, nullable=False)
    # Free-text label staff pick at upload time (e.g. "Fees", "Hostel") - lets
    # the documents list be browsed/filtered by topic instead of only by
    # filename, and gives future retrieval work something to weight on.
    category: Mapped[str | None] = mapped_column(Text)
    # sha256 of the uploaded bytes - lets the upload endpoint warn staff
    # when a file they're about to add looks identical to one that's
    # already in the knowledge base, before it gets processed a second time.
    content_hash: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="documents")
    uploaded_by_membership: Mapped["StaffCollege"] = relationship("StaffCollege", primaryjoin=("and_(Document.college_id == StaffCollege.college_id, " "Document.uploaded_by == StaffCollege.staff_id)"), foreign_keys="[Document.college_id, Document.uploaded_by]", viewonly=True)

    __table_args__ = (
        CheckConstraint("document_status IN ('processing', 'success', 'failed')", name="documents_document_status_check"),
        ForeignKeyConstraint(["college_id", "uploaded_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"]),
        UniqueConstraint("college_id", "document_id"),
        Index("ix_documents_college_id", "college_id"),
        Index("ix_documents_college_content_hash", "college_id", "content_hash")
    )