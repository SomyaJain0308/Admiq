from datetime import datetime

from backend.app.database import Base
from backend.app.models.College import College

from sqlalchemy import Boolean, ForeignKey, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CollegeStaff(Base):
    __tablename__ = "college_staff"

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_name: Mapped[str] = mapped_column(Text, nullable=False)
    staff_email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college_memberships: Mapped[list["StaffCollege"]] = relationship(back_populates="staff_member", cascade="all, delete-orphan")



class StaffCollege(Base):
    __tablename__ = "staff_colleges"

    staff_id: Mapped[int] = mapped_column(Integer, ForeignKey("college_staff.staff_id", ondelete="CASCADE"), primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    staff_member: Mapped["CollegeStaff"] = relationship(back_populates="college_memberships")
    college: Mapped["College"] = relationship(back_populates="staff_memberships")

    __table_args__ = (
        UniqueConstraint("college_id", "staff_id"),
        Index("ix_staff_colleges_college_id", "college_id"), 
        Index("ix_staff_colleges_staff_id", "staff_id")
    )