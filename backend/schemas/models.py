from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, TypedDict



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
    search_query: str
    retrieval_retry_count: int
    previous_assistant_message: str | None

    # retrieve
    relevant_documents: str
    best_distance: float
    passing_chunk_count: int

    # flag_low_confidence
    needs_human_review: bool

    # build_prompt
    prompt: str

    # process / try_fallback
    primary_retry_count: int
    fallback_retry_count: int
    response: str
    updated_session_summary: str
    sources: str
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
    sources: str = Field(default="", description=("""Comma-separated list of source document titles or IDs cited in the response, e.g. 'admissions_faq.pdf, tuition_2026.pdf'. Use an empty string if no sources were used. Do not use any other delimiter. Only list Unique chunks never add repetetive chunks."""))
    wants_human_handoff: bool = Field(default=False)


class QueryRewrite(BaseModel):
    needs_retrieval: bool = Field(description="False for greetings, thanks, acknowledgments, or small talk that don't need document lookup. True for anything asking about fees, courses, eligibility, deadlines, hostel, placements, documents, or admissions process.")
    search_query: str = Field(default="", description="Empty if needs_retrieval is False.")