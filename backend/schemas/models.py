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
    db: object # USED
    college_id: int #USED
    student_id: int # USED
    session_id: int # USED
    request_id: int
    input_tokens: int
    output_tokens: int
    query: str # USED
    prompt: str # USED
    response: str # USED
    updated_session_summary: str # USED
    sources: str # USED
    error: Optional[str]
    error_type: Optional[str]
    retrieval_degraded: bool
    primary_retry_count: int
    fallback_retry_count: int
    model_used: str
    student_summary: str | None
    session_summary: str | None



class AgentTurnOutput(BaseModel): # What the assistant sends back
    response: str
    updated_session_summary: str
    sources: str = Field(default="", description=("""Comma-separated list of source document titles or IDs cited in the response, e.g. 'admissions_faq.pdf, tuition_2026.pdf'. Use an empty string if no sources were used. Do not use any other delimiter. Only list Unique chunks never add repetetive chunks."""))


















class ChatRequest(BaseModel):
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The student's message to the llm"
    )
    college_id: int
    thread_id: str = Field(
        default="default",
        description="Conversation thread ID"
    ) 

class ChatResponse(BaseModel):
    response: str
    thread_id: str
    model_used: str
    sources: list[str] = []
    cached: bool = False
    processing_time_ms: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HealthResponse(BaseModel):
    status: str = "Healthy"
    environment: str
    version: str = "1.0.0"
    checks: dict = {}

class MetricsResponse(BaseModel):
    total_requests: int
    total_errors: int
    error_rate: str
    avg_latency_ms: float
    total_input_tokens: int
    total_output_tokens: int

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    request_id: str | None = None
