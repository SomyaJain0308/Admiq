from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.Course import Course
from backend.app.database import Base

from sqlalchemy import Boolean, CheckConstraint, ForeignKeyConstraint, Index, Integer, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship


# Keep this in sync with schemas/eligibility.py's RULE_CONFIG_MODELS and the
# CHECK constraint below - it's the single source of truth for which rule
# templates the staff UI (and eligibility_service's question builder) support.
RULE_TYPES = ("min_percentage", "min_subject_marks", "required_stream", "entrance_cutoff", "category_cutoff", "custom_yesno", "best_of_n_subjects", "domicile_quota", "age_limit")


class EligibilityRule(Base):
    """
    One configurable, order-sensitive pass/fail check on a Course.
    `config` is a JSONB blob whose shape depends on `rule_type` (validated at
    the API layer against schemas/eligibility.py's per-type Pydantic models)
    rather than a fixed set of columns, so staff can express a new course's
    criteria without a code change or migration. See eligibility_service.py
    for how a rule becomes a WhatsApp question and how an answer is scored.
    """
    __tablename__ = "eligibility_rules"

    rule_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, nullable=False)
    course_id: Mapped[int] = mapped_column(Integer, nullable=False)
    rule_type: Mapped[str] = mapped_column(Text, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Flow asks rules in this order and stops at the first failure (fail-fast)
    # - staff should put their highest-dropout filter first.
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    # Bumped on every PATCH (config or is_active change) - onupdate fires at
    # the SQLAlchemy level whenever the ORM object is actually dirty, so a
    # PATCH that changes nothing doesn't create a false signal. Paired with
    # eligibility_rule_history below for the "what changed and when" story
    # updated_at alone can't tell (a bumped timestamp with no prior value).
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now(), onupdate=func.now())

    course: Mapped["Course"] = relationship(back_populates="eligibility_rules")

    __table_args__ = (
        CheckConstraint("rule_type IN ('min_percentage','min_subject_marks','required_stream','entrance_cutoff','category_cutoff','custom_yesno','best_of_n_subjects','domicile_quota','age_limit')", name="eligibility_rules_rule_type_check"),
        UniqueConstraint("college_id", "rule_id"),
        ForeignKeyConstraint(["college_id", "course_id"], ["courses.college_id", "courses.course_id"], ondelete="CASCADE"),
        Index("ix_eligibility_rules_college_id_course_id", "college_id", "course_id"),
    )
