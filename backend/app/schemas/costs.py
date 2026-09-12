from datetime import date, datetime

from pydantic import BaseModel, Field


class CostEventDetail(BaseModel):
    """One raw cost_events row - for the per-student drill-down so someone
    can check exactly which billed calls a single question produced, rather
    than trusting the aggregated total on faith."""

    cost_event_id: int
    cost_type: str
    stage: str | None
    model: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    session_id: int | None
    created_at: datetime


class DailyCost(BaseModel):
    date: date
    total_cost_usd: float


class CostByModel(BaseModel):
    model: str
    total_cost_usd: float
    total_tokens: int = Field(description="input_tokens + output_tokens summed for this model. 0 for embedding models, which report input tokens only, still summed here.")


class WhatsAppCostBreakdown(BaseModel):
    category: str = Field(description="'session', 'utility', or 'marketing' - see cost_service.whatsapp_conversation_cost_usd.")
    total_cost_usd: float
    message_count: int = Field(description="Number of billed sends in this category (only successful sends generate a cost_events row).")


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

    # --- Trend ---
    daily_cost_last_30_days: list[DailyCost] = Field(default_factory=list, description="All cost_type spend bucketed by UTC day for the trailing 30 days, oldest first, zero-filled for days with no activity.")
    projected_monthly_cost_usd: float = Field(description="A simple run-rate projection - (total_cost_usd_last_7_days / 7) * 30 - not a real forecast, just a quick 'if this week repeats' number.")

    # --- Further breakdowns ---
    cost_by_model: list[CostByModel] = Field(default_factory=list, description="LLM/embedding spend broken down by underlying model name, highest first. Excludes WhatsApp costs, which aren't model-attributed.")
    whatsapp_cost_breakdown: list[WhatsAppCostBreakdown] = Field(default_factory=list, description="WhatsApp spend by conversation category (session/utility/marketing), each with its billed-send count.")

    # --- Knowledge base overhead ---
    document_ingestion_cost_usd: float = Field(description="Total embedding cost attributable to the document_ingestion stage - a college-level knowledge-base cost, not attributable to any one student.")
    document_count: int = Field(description="Number of documents uploaded for this college (any status), the denominator for avg_cost_per_document_usd.")
    avg_cost_per_document_usd: float | None = Field(default=None, description="document_ingestion_cost_usd / document_count. None if no documents have been uploaded yet.")

    # --- Per-reply unit economics ---
    avg_cost_per_assistant_message_usd: float | None = Field(default=None, description="Total LLM cost / count of assistant-authored messages - the per-reply cost, independent of how long a session runs. None if the assistant hasn't sent any messages yet.")
