from datetime import datetime
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from backend.app.models.College import College
    from backend.app.models.LowConfidenceQuery import LowConfidenceQuery
    from backend.app.models.Document import Document
from backend.app.database import Base


from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int | None] = mapped_column(Integer)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    chunk_content: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_context: Mapped[str | None] = mapped_column(Text) # If u change this change rag/retrieval.py 
    embedding: Mapped[list[float]] = mapped_column(Vector(768), nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    source_query_id: Mapped[int | None] = mapped_column(Integer)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    college: Mapped["College"] = relationship(back_populates="chunks")
    document: Mapped["Document | None"] = relationship("Document", primaryjoin=("and_(Chunk.college_id == Document.college_id, " "Chunk.document_id == Document.document_id)"), foreign_keys="[Chunk.college_id, Chunk.document_id]", viewonly=True)
    source_query: Mapped["LowConfidenceQuery | None"] = relationship("LowConfidenceQuery", primaryjoin=("and_(Chunk.college_id == LowConfidenceQuery.college_id, " "Chunk.source_query_id == LowConfidenceQuery.query_id)"), foreign_keys="[Chunk.college_id, Chunk.source_query_id]", viewonly=True)

    __table_args__ = (
        ForeignKeyConstraint(["college_id", "document_id"], ["documents.college_id", "documents.document_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "source_query_id"], ["low_confidence_queries.college_id", "low_confidence_queries.query_id"]),
        CheckConstraint("source_type IN ('document', 'staff_answer')", name="chunks_source_type_check"),
        CheckConstraint("(source_type = 'document' AND document_id IS NOT NULL) OR" "(source_type = 'staff_answer' AND source_query_id IS NOT NULL)", name="chunks_source_reference_check"),
        CheckConstraint("source_type = 'staff_answer' OR expires_at IS NULL", name="chunks_document_no_expiry_check"),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
        Index("ix_chunks_college_id", "college_id"),
        Index("ix_chunks_document_id", "document_id"),
        Index("ix_chunk_content", "chunk_content"),
    )