from datetime import date

from pydantic import BaseModel, Field


class StaffResolutionCount(BaseModel):
    staff_id: int
    staff_name: str
    resolved_count: int


class CourseInterestCount(BaseModel):
    course_interest: str
    count: int


class DailyMessageCount(BaseModel):
    date: date
    count: int


class DashboardStatsResponse(BaseModel):
    # --- Queue / staff SLA ---
    avg_resolution_seconds: float | None = Field(default=None, description="Average time between a query being flagged and resolved, across all-time resolved queries.")
    median_resolution_seconds: float | None = Field(default=None, description="Median resolution time, less skewed by a handful of very old outliers than the average.")
    resolved_today: int = Field(description="Low-confidence queries resolved since the start of today (UTC).")
    resolved_last_7_days: int = Field(description="Low-confidence queries resolved in the trailing 7 days.")
    oldest_open_query_age_seconds: float | None = Field(default=None, description="How long the longest-waiting still-open query has been flagged, in seconds. None if the queue is empty.")
    resolutions_by_staff_last_7_days: list[StaffResolutionCount] = Field(default_factory=list, description="Who resolved how many queries in the trailing 7 days, sorted highest first.")

    # --- Lead funnel ---
    new_students_today: int = Field(description="Students first messaging in since the start of today (UTC).")
    new_students_last_7_days: int = Field(description="New students in the trailing 7 days.")
    new_students_prev_7_days: int = Field(description="New students in the 7 days before that, for a week-over-week comparison.")
    newly_hot_leads_last_7_days: int = Field(description="Students currently scored 'hot' whose score last updated to that level within the trailing 7 days.")
    unassigned_hot_leads: int = Field(description="Currently 'hot' students with nobody assigned to them - the at-risk-of-falling-through-the-cracks count.")
    course_interest_breakdown: list[CourseInterestCount] = Field(default_factory=list, description="Top course interests by student count, most popular first.")

    # --- Conversation volume & engagement ---
    messages_today: int = Field(description="Messages of any kind (student, assistant, staff) sent today so far.")
    messages_last_7_days: list[DailyMessageCount] = Field(default_factory=list, description="Daily message volume for the trailing 7 days, oldest first, zero-filled for days with no activity.")
    active_sessions: int = Field(description="Sessions currently open (a student is, or very recently was, mid-conversation).")
    bounce_rate_pct: float | None = Field(default=None, description="Percent of sessions with 2 or fewer total messages - a proxy for students dropping off almost immediately. None if there's no session data yet.")

    # --- Knowledge base / bot health (excludes thumbs-up/down, tracked separately) ---
    self_serve_rate_pct: float | None = Field(default=None, description="Percent of assistant answers that did NOT need to be escalated to the low-confidence queue. None if the assistant hasn't sent any messages yet.")
    failed_documents: int = Field(description="Uploaded documents that failed processing and never made it into the knowledge base.")
    avg_document_quality_score: float | None = Field(default=None, description="Average extraction quality score across successfully processed documents. None if there are none yet.")
    staff_answers_added_last_7_days: int = Field(description="New reusable answers added to the knowledge base from staff replies in the trailing 7 days.")
