from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
from backend.app.database import Base

from sqlalchemy import ForeignKey, Index, Integer, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class WhatsAppNumber(Base):
    __tablename__ = "whatsapp_numbers"

    number_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # Meta's ID, present in every webhook payload
    display_number: Mapped[str | None] = mapped_column(Text)  # human-readable, e.g. +91XXXXXXXXXX
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    whatsapp_business_account_id: Mapped[str] = mapped_column(Text, nullable=False)

    college: Mapped["College"] = relationship(back_populates="whatsapp_numbers")

    __table_args__ = (Index("ix_whatsapp_numbers_college_id", "college_id"),)
