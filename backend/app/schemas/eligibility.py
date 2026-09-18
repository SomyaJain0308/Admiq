from pydantic import BaseModel, Field
from typing import Literal


# --- Per-rule-type config shapes ---------------------------------------
# Each one maps to a single WhatsApp question in eligibility_service.py.
# Keep RULE_CONFIG_MODELS' keys in sync with EligibilityRule.RULE_TYPES and
# the DB CHECK constraint - this is the validation layer for the JSONB
# `config` blob staff build through the dashboard.

class MinPercentageConfig(BaseModel):
    """A single overall-percentage cutoff, e.g. '60% or above in 12th'."""
    label: str = Field(description="What this percentage is of, e.g. '12th percentage'")
    min_value: float = Field(ge=0, le=100)


class MinSubjectMarksConfig(BaseModel):
    """A minimum-marks requirement in one named subject."""
    subject: str
    min_value: float = Field(ge=0, le=100)


class RequiredStreamConfig(BaseModel):
    """Student must have studied one of a set of streams (shown as a list message)."""
    allowed_streams: list[str] = Field(min_length=1)


class EntranceCutoffConfig(BaseModel):
    """An entrance-exam percentile or rank cutoff."""
    exam_name: str
    metric: Literal["percentile", "rank"] = "percentile"
    threshold: float = Field(gt=0)


class CategoryCutoffConfig(BaseModel):
    """
    Same idea as min_percentage/entrance_cutoff, but the threshold varies by
    reservation category. Asking category is handled once per flow (not once
    per rule) - see eligibility_service.requires_category.
    """
    metric_label: str = Field(description="What the threshold measures, e.g. '12th percentage' or 'JEE Main percentile'")
    thresholds: dict[str, float] = Field(min_length=1, description="category key -> threshold, e.g. {'general': 60, 'obc': 55, 'sc': 50, 'st': 50, 'ews': 55}")
    higher_is_better: bool = True


class CustomYesNoConfig(BaseModel):
    """Escape hatch for one-off criteria that don't fit a template."""
    question: str
    pass_answer: Literal["yes", "no"] = "yes"


RULE_CONFIG_MODELS: dict[str, type[BaseModel]] = {
    "min_percentage": MinPercentageConfig,
    "min_subject_marks": MinSubjectMarksConfig,
    "required_stream": RequiredStreamConfig,
    "entrance_cutoff": EntranceCutoffConfig,
    "category_cutoff": CategoryCutoffConfig,
    "custom_yesno": CustomYesNoConfig,
}

RULE_TYPE_LABELS: dict[str, str] = {
    "min_percentage": "Minimum overall percentage",
    "min_subject_marks": "Minimum marks in a subject",
    "required_stream": "Required stream",
    "entrance_cutoff": "Entrance exam cutoff",
    "category_cutoff": "Category-specific cutoff",
    "custom_yesno": "Custom yes/no requirement",
}


# --- CRUD schemas --------------------------------------------------------

class EligibilityRuleCreate(BaseModel):
    rule_type: Literal["min_percentage", "min_subject_marks", "required_stream", "entrance_cutoff", "category_cutoff", "custom_yesno"]
    config: dict
    is_active: bool = True


class EligibilityRuleUpdate(BaseModel):
    config: dict | None = None
    is_active: bool | None = None


class EligibilityRuleResponse(BaseModel):
    rule_id: int
    course_id: int
    rule_type: str
    config: dict
    order_index: int
    is_active: bool
    # Not stored - filled in by the router from eligibility_service so staff
    # can see exactly what the student will be asked, in their own words.
    generated_question: str | None = None

    model_config = {"from_attributes": True}


class RuleReorderRequest(BaseModel):
    rule_ids: list[int] = Field(description="Every rule_id belonging to the course, in the new order")


class CourseCreate(BaseModel):
    course_name: str = Field(min_length=1)
    # A "programme type" course to nest this one under (e.g. create "B.Tech"
    # first, then "Computer Science" with parent_course_id set to B.Tech's
    # id) - see services/eligibility_service.py for how this drives the
    # WhatsApp course-picker flow. Omit/None for a normal top-level course.
    parent_course_id: int | None = None


class CourseUpdate(BaseModel):
    course_name: str | None = None
    is_published: bool | None = None
    admission_procedure: str | None = None
    # Explicitly settable to null (unlike the other optional fields above,
    # which just mean "leave unchanged" when omitted) - PATCH with
    # {"parent_course_id": null} is how staff move a branch back to being a
    # top-level course. The router only treats this as "move to root" when
    # the key is actually present in the request body (see update_course).
    parent_course_id: int | None = None


class CourseResponse(BaseModel):
    course_id: int
    college_id: int
    course_name: str
    parent_course_id: int | None = None
    is_published: bool
    order_index: int
    admission_procedure: str | None = None
    rule_count: int = 0

    model_config = {"from_attributes": True}


class CourseDetailResponse(CourseResponse):
    rules: list[EligibilityRuleResponse] = []
    # Rules inherited from ancestor programme-type courses (see
    # eligibility_service.get_effective_rules) - read-only here; staff edit
    # them on the ancestor course itself, not from a branch's editor. None
    # of this course's own `rules` are duplicated into this list.
    inherited_rules: list[EligibilityRuleResponse] = []
    programme_path: str | None = None


# --- Analytics -------------------------------------------------------------
# Backed by eligibility_events (models/EligibilityEvent.py) - see
# api/v1/routers/eligibility.py's /eligibility-analytics endpoint.

class CourseEligibilityStats(BaseModel):
    course_id: int
    course_name: str
    passed: int
    failed: int
    borderline: int
    total_completed: int = Field(description="passed + failed + borderline - students who reached a final verdict on this course, not counting cancels/timeouts.")
    pass_rate: float = Field(description="passed / total_completed, 0.0 if nobody's finished this course's check yet.")


class DropOffPoint(BaseModel):
    course_id: int | None = Field(description="None if the drop-off happened before a course was even picked (e.g. at the initial trigger-confirmation step).")
    course_name: str | None = None
    step: str = Field(description="Which eligibility_service.py flow step the student was on - see EligibilityEvent.FLOW_STEPS.")
    rule_index: int | None = Field(description="0-based position in the course's rule list at the time, only set for step='await_rule'.")
    rule_description: str | None = Field(description="Best-effort label for that rule from the course's CURRENT active rule list - null if the rule list has since changed enough that this historical index can't be confidently mapped.")
    drop_offs: int = Field(description="Count of cancelled + timed_out events at this exact point.")


class EligibilityAnalyticsResponse(BaseModel):
    course_stats: list[CourseEligibilityStats] = Field(description="One entry per course that's had at least one completed (passed/failed/borderline) check, sorted by total_completed descending.")
    drop_off_points: list[DropOffPoint] = Field(description="Every distinct (course, step, rule_index) combination that's seen a cancel or timeout, sorted by drop_offs descending - the top entry is literally 'where students give up most'.")


# --- Rule-conflict / sanity validation --------------------------------------
# Backed by eligibility_service.find_rule_conflicts - schema-shape validation
# (RULE_CONFIG_MODELS above) catches a malformed rule; this catches a
# *combination* of otherwise-valid rules that can't actually be satisfied,
# or a category the WhatsApp flow can ask about but a rule doesn't cover.

class RuleConflict(BaseModel):
    severity: Literal["error", "warning"] = Field(description="'error' = this combination can never pass for anyone; 'warning' = worth a staff look but not necessarily wrong (e.g. a narrower rule elsewhere already excludes the gap).")
    rule_ids: list[int] = Field(description="The rule(s) involved, for the UI to highlight.")
    message: str


class RuleConflictsResponse(BaseModel):
    conflicts: list[RuleConflict] = []
