from pydantic import BaseModel, Field
from datetime import datetime
from typing import Literal, Optional, TypedDict



class InboundWhatsAppMessage(BaseModel):
    whatsapp_business_account_id: str
    phone_number_id: str
    display_phone_number: str
    whatsapp_user_id: str
    student_name: str | None = None
    student_phone: str
    whatsapp_message_id: str
    whatsapp_timestamp: datetime
    message_type: str
    content: str
    raw_payload: dict
    


class AgentState(TypedDict): # dictionary that gets passed from node to node, and each node can read it and add to it.
    db: object
    college_id: int
    student_id: int
    session_id: int
    query: str

    # resolve_query / re_query
    needs_retrieval: bool
    pending_queries: list[str]
    resolved_chunks: list
    retrieval_retry_count: int
    previous_assistant_message: str | None

    # retrieve
    relevant_documents: str
    best_distance: float

    # flag_low_confidence
    needs_human_review: bool

    # build_prompt
    prompt: str

    # process / try_fallback
    primary_retry_count: int
    fallback_retry_count: int
    response: str
    updated_session_summary: str
    sources: list[str]
    wants_human_handoff: bool
    error: Optional[str]
    model_used: str

    # token accounting, threaded through every LLM-calling node
    input_tokens: int
    output_tokens: int

    # carried through from main.py, read by build_system_prompt
    student_summary: str | None
    session_summary: str | None

class AgentTurnOutput(BaseModel): # What the assistant sends back
    response: str
    updated_session_summary: str
    sources: list[str] = Field(default_factory=list, description="list of source filenames/queries used to answer, empty list if none were used")
    wants_human_handoff: bool = Field(default=False)


class QueryRewrite(BaseModel):
    needs_retrieval: bool = Field(description="False for greetings, thanks, acknowledgments, or small talk that don't need document lookup. True for anything asking about fees, courses, eligibility, deadlines, hostel, placements, documents, or admissions process.")
    search_queries: list[str] = Field(default_factory=list, description="1-4 focused search queries. Use 1 for a single-topic question. Only split into multiple when the student is genuinely asking about multiple distinct topics/courses/comparisons in one message (e.g. 'compare CSE and ECE fees' -> 2 queries, one per course). Empty if needs_retrieval is False.")


class ChatTestRequest(BaseModel):
    college_id: int
    student_phone: str
    message: str
    student_name: str | None = None


class ChatTestResponse(BaseModel):
    response: str
    model_used: str
    sources: list[str]
    wants_human_handoff: bool
    best_distance: float | None
    session_id: int
    student_id: int


class StudentProfileUpdate(BaseModel):
    summary: str = Field(description="Updated long-term profile summary, merging the existing profile with this session.")
    course_interest: str | None = Field(default=None, description="The course/program the student is currently most interested in - ONLY if explicitly stated by the student this session. Never invent a value the student didn't state. Empty if not mentioned. If student seems interested in multiple program return a str, for e.g. 'cse, ece, cse(ai/ml)' just like this.")
    academic_score_updates: dict[str, float] = Field(default_factory=dict, description="Any NEW or UPDATED academic scores explicitily stated by the student this session, e.g. {'jee_main_percentile': 95.2, 'class_12_percentage': 92.36}. Use consistent snake_case keys. Never invent a value the student didn't state. Empty if none mentioned.")
    interest_signal: Literal["positive", "negative", "neutral"] = Field(description="'positive' if the student showed genuine engagement or interest in moving forward (asking about next steps, deadlines, documents). 'negative' if they explicitily said they're not interested or are going elsewhere. 'neutral' if the session was purely informational or inconclusive." )