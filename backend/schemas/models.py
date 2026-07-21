from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Optional, TypedDict, Annotated, List
from langgraph.graph.message import add_messages
from langchain_core.message import BaseMessage


class AgentState(TypedDict): # dictionary that gets passed from node to node, and each node can read it and add to it.
    db: object
    college_id: int
    messages: Annotated[list[BaseMessage], add_messages]
    error: Optional[str]
    retry_count: int
    model_used: str
    sources: List[str]
    student_summary: str | None
    session_summary: str | None


class AgentTurnOutput(BaseModel):
    reply: str
    updated_session_summary: str


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
