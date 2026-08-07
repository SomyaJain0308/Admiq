from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.CollegeStaff_StaffCollege import StaffCollege
    from backend.app.models.Document import Document
    from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
    from backend.app.models.WhatsappNumber import WhatsAppNumber
    from backend.app.models.Student import Student
    from backend.app.models.Message import Message
    from backend.app.models.Chunk import Chunk
    from backend.app.models.StudentSession import StudentSession
from backend.app.database import Base

from sqlalchemy import Integer, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship



class College(Base):
    __tablename__ = "colleges"

    college_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_name: Mapped[str] = mapped_column(Text, nullable=False)
    college_phone: Mapped[str] = mapped_column(Text, nullable=False)
    college_email: Mapped[str] = mapped_column(Text, nullable=False)
    college_context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    students: Mapped[list["Student"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    whatsapp_numbers: Mapped[list["WhatsAppNumber"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    staff_memberships: Mapped[list["StaffCollege"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    sessions: Mapped[list["StudentSession"]] = relationship(back_populates="college", cascade="all, delete-orphan")
