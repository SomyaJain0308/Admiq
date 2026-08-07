from datetime import datetime

from backend.app.database import Base
from backend.app.models.College import College
from backend.app.models.CollegeStaff_StaffCollege import StaffCollege

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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="documents")
    uploaded_by_membership: Mapped["StaffCollege"] = relationship("StaffCollege", primaryjoin=("and_(Document.college_id == StaffCollege.college_id, " "Document.uploaded_by == StaffCollege.staff_id)"), foreign_keys="[Document.college_id, Document.uploaded_by]", viewonly=True)

    __table_args__ = (
        CheckConstraint("document_status IN ('processing', 'success', 'failed')", name="documents_document_status_check"),
        ForeignKeyConstraint(["college_id", "uploaded_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"]),
        UniqueConstraint("college_id", "document_id"),
        Index("ix_documents_college_id", "college_id")
    )