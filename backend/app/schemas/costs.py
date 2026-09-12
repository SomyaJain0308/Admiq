from pydantic import BaseModel, Field


class CostByType(BaseModel):
    cost_type: str = Field(description="'llm', 'embedding', or 'whatsapp'.")
    total_cost_usd: float
    percent_of_total: float


class CostByStage(BaseModel):
    stage: str = Field(description="e.g. 'primary', 'fallback', 'resolve_query', 're_query', 'retrieval_embedding', 'document_ingestion', 'whatsapp_session', 'whatsapp_utility', 'whatsapp_marketing', 'reengagement'.")
    total_cost_usd: float
    total_tokens: int = Field(description="input_tokens + output_tokens summed for this stage. 0 for whatsapp stages, which aren't token-based.")


class TopCostStudent(BaseModel):
    student_id: int
    student_name: str | None
    total_cost_usd: float


class CostStatsResponse(BaseModel):
    # --- Totals & trend ---
    total_cost_usd_all_time: float = Field(description="Every cost_events row for this college, ever.")
    total_cost_usd_last_7_days: float
    total_cost_usd_prev_7_days: float = Field(description="The 7 days before that, for a week-over-week comparison.")

    # --- Per-student unit economics ---
    # Computed across EVERY student in the college (zero-cost students count
    # as $0), not just students who've triggered a cost event - this is
    # meant to answer "what does a student cost us", including the ones who
    # never engaged, which is the honest denominator for a per-acquired-
    # student cost figure.
    total_students: int
    avg_cost_per_student_usd: float
    median_cost_per_student_usd: float = Field(description="Less skewed by a handful of very chatty (or very retried/fallback-heavy) students than the average.")
    p95_cost_per_student_usd: float = Field(description="The expensive-tail cutoff - 95% of students cost less than this.")
    top_students_by_cost: list[TopCostStudent] = Field(default_factory=list, description="The 10 costliest students all-time, highest first.")

    # --- Per-session unit economics ---
    total_sessions: int
    avg_cost_per_session_usd: float
    median_cost_per_session_usd: float

    # --- Breakdowns ---
    cost_by_type: list[CostByType] = Field(default_factory=list, description="llm vs embedding vs whatsapp, as a share of total_cost_usd_all_time.")
    cost_by_stage: list[CostByStage] = Field(default_factory=list, description="Top cost stages, highest first - useful for spotting where retries/fallback are burning money.")

    # --- Efficiency ---
    sessions_with_low_confidence_escalation: int = Field(description="Sessions that produced at least one low-confidence-queue entry.")
    avg_cost_per_escalated_session_usd: float | None = Field(default=None, description="Average all-time cost of sessions that hit the low-confidence queue. None if there are none yet.")
    avg_cost_per_non_escalated_session_usd: float | None = Field(default=None, description="Average all-time cost of sessions that never escalated - the comparison point for the above. None if there are none yet.")
