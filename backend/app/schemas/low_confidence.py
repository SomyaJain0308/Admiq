from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional

class LowConfidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    query_id: int
    college_id: int
    student_id: int
    question_message_id: int
    question_content: str
    answer_message_id: int
    answer_content: str
    resolved: bool
    resolved_at: Optional[datetime] = Field(default=None, description="Timestamp when the query was resolved, if applicable.")
    resolved_by: Optional[int] = Field(default=None, description="Staff ID of the user who resolved the query, if applicable.")


class ReconstructedAnswer(BaseModel):
    question: str = Field(description="Self-contained version of the student's question, with all references resolved.")
    answer: str = Field(description="Concise answer based on the staff reply.")