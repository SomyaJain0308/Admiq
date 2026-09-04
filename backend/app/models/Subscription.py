from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
from backend.app.database import Base

from sqlalchemy import ForeignKey, Integer, func, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


class CollegeSubscription(Base):
    __tablename__ = "college_subscriptions"

    subscription_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), unique=True, nullable=False)
    plan_tier: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default="pending") # pending, active, past_due, cancelled
    current_period_end: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    razorpay_customer_id: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="subscription")