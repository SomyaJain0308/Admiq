from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class ConflictChunkInfo(BaseModel):
    chunk_id: int
    content: str
    source_type: str  # 'document' | 'staff_answer'
    # Human-readable origin: the document's file name, or the staff-answer's
    # original question (for a reactive entry) / "Knowledge base entry" (for
    # a proactive one).
    source_label: str
    document_id: Optional[int] = None
    is_expired: bool = False


class KnowledgeConflictResponse(BaseModel):
    conflict_id: int
    college_id: int
    status: str
    explanation: str
    similarity_distance: Optional[float] = None
    new_chunk: ConflictChunkInfo
    existing_chunk: ConflictChunkInfo
    created_at: datetime
    resolved_by: Optional[int] = None
    resolved_by_name: Optional[str] = None
    resolved_at: Optional[datetime] = None


class KnowledgeConflictListResponse(BaseModel):
    items: list[KnowledgeConflictResponse]
    total: int
    page: int
    page_size: int
