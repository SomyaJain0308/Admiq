from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class KnowledgeBaseEntry(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    chunk_id: int
    question: str
    answer: str
    # "proactive" - staff wrote this Q&A directly, with no flagged student
    # question behind it. "reactive" - it was reconstructed from a staff
    # reply to a flagged low-confidence query (source_query_id set).
    origin: str
    source_query_id: Optional[int] = None
    # The student's actual flagged question, for reactive entries only -
    # useful context distinct from the (possibly LLM-reworded) reconstructed
    # `question` field above.
    original_question: Optional[str] = None
    expires_at: Optional[datetime] = None
    is_expired: bool
    retrieval_count: int
    last_retrieved_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None
    created_by_name: Optional[str] = None
    # How many existing entries this write was just flagged as conflicting
    # with (see rag/conflict_detection.py) - not persisted on the chunk
    # itself, just surfaced once here so the UI can toast about it right
    # after a save. Always 0 on a plain read (list_knowledge_base never
    # re-runs detection).
    conflicts_flagged: int = 0


class KnowledgeBaseListResponse(BaseModel):
    items: list[KnowledgeBaseEntry]
    total: int
    page: int
    page_size: int


class CreateKnowledgeBaseEntry(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    answer: str = Field(min_length=1, max_length=4000)
    expires_at: Optional[datetime] = None


class UpdateKnowledgeBaseEntry(BaseModel):
    question: Optional[str] = Field(default=None, min_length=1, max_length=2000)
    answer: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    # expires_at=None is ambiguous ("don't change it" vs "clear it"), so
    # clearing an existing expiry is an explicit, separate flag rather than
    # inferred from the field being absent/null.
    expires_at: Optional[datetime] = None
    clear_expiry: bool = False
