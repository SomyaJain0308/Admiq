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
    resolved_by: Optional[str] = Field(default=None, description="Identifier of the user who resolved the query, if applicable.")
    