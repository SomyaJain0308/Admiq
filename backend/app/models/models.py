from datetime import datetime

from backend.app.database import Base

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, ForeignKeyConstraint, Index, Integer, Numeric, UniqueConstraint, func, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship




class College(Base):
    __tablename__ = "colleges"

    college_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_name: Mapped[str] = mapped_column(Text, nullable=False)
    college_phone: Mapped[str] = mapped_column(Text, nullable=False)
    college_email: Mapped[str] = mapped_column(Text, nullable=False)
    college_context: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    students: Mapped[list["Student"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    whatsapp_numbers: Mapped[list["WhatsAppNumber"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    staff_memberships: Mapped[list["StaffCollege"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    messages: Mapped[list["Message"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    sessions: Mapped[list["StudentSession"]] = relationship(back_populates="college", cascade="all, delete-orphan")


class WhatsAppNumber(Base):
    __tablename__ = "whatsapp_numbers"

    number_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    phone_number_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # Meta's ID, present in every webhook payload
    display_number: Mapped[str | None] = mapped_column(Text)  # human-readable, e.g. +91XXXXXXXXXX
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    whatsapp_business_account_id: Mapped[str] = mapped_column(Text, nullable=False)

    college: Mapped["College"] = relationship(back_populates="whatsapp_numbers")

    __table_args__ = (Index("ix_whatsapp_numbers_college_id", "college_id"),)



class CollegeStaff(Base):
    __tablename__ = "college_staff"

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    staff_name: Mapped[str] = mapped_column(Text, nullable=False)
    staff_email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default="true", nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college_memberships: Mapped[list["StaffCollege"]] = relationship(back_populates="staff_member", cascade="all, delete-orphan")



class StaffCollege(Base):
    __tablename__ = "staff_colleges"

    staff_id: Mapped[int] = mapped_column(Integer, ForeignKey("college_staff.staff_id", ondelete="CASCADE"), primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    staff_member: Mapped["CollegeStaff"] = relationship(back_populates="college_memberships")
    college: Mapped["College"] = relationship(back_populates="staff_memberships")

    __table_args__ = (
        UniqueConstraint("college_id", "staff_id"),
        Index("ix_staff_colleges_college_id", "college_id"), 
        Index("ix_staff_colleges_staff_id", "staff_id")
    )



class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_phone: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_user_id: Mapped[str] = mapped_column(Text, nullable=False)
    student_name: Mapped[str | None] = mapped_column(Text)
    course_interest: Mapped[str | None] = mapped_column(Text)
    academic_scores: Mapped[dict | None] = mapped_column(JSONB)  # e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary: Mapped[str | None] = mapped_column(Text)
    student_status: Mapped[str] = mapped_column(Text, server_default="new")
    assigned_to: Mapped[int | None] = mapped_column(Integer)
    internal_notes: Mapped[str | None] = mapped_column(Text)  # manual staff notes, separate from AI-generated summary
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("college_id", "student_id"),
        UniqueConstraint("college_id", "whatsapp_user_id"),
        UniqueConstraint("college_id", "student_phone"),
        CheckConstraint("student_status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested')", name="students_student_status_check"), # Add more later if required
        Index("ix_students_college_id", "college_id"),
        Index("ix_students_college_id_student_status", "college_id", "student_status"),
        ForeignKeyConstraint(["college_id", "assigned_to"], ["staff_colleges.college_id", "staff_colleges.staff_id"])
    )

    college: Mapped["College"] = relationship(back_populates="students")
    messages: Mapped[list["Message"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="messages")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="low_confidence_queries")
    assigned_staff_membership: Mapped["StaffCollege | None"] = relationship("StaffCollege", primaryjoin=("and_(Student.college_id == StaffCollege.college_id, " "Student.assigned_to == StaffCollege.staff_id)"), foreign_keys="[Student.college_id, Student.assigned_to]", viewonly=True)
    sessions: Mapped[list["StudentSession"]] = relationship(back_populates="student", cascade="all, delete-orphan", overlaps="sessions")



class StudentSession(Base):
    __tablename__ = "student_sessions"

    session_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=func.now())
    last_message_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, server_default=func.now())
    ended_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    session_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="active")
    session_summary: Mapped[str | None] = mapped_column(Text)
    profile_processed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    total_tokens_used: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")


    student: Mapped["Student"] = relationship(back_populates="sessions", overlaps="sessions")
    college: Mapped["College"] = relationship(back_populates="sessions", overlaps="sessions,student")
    messages: Mapped[list["Message"]] = relationship(back_populates="session", overlaps="messages,messages")

    __table_args__ = (
        CheckConstraint("session_status IN ('active', 'closed')"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        UniqueConstraint("college_id", "session_id"),
        Index("one_active_session_per_student", "college_id", "student_id", unique=True, postgresql_where=(session_status == "active")),
        Index("ix_sessions_college_id_student_id_session_status", "college_id", "student_id", "session_status"), 
        Index("ix_sessions_last_message_at", "last_message_at"), 
    )



class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    messager_role: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    sources: Mapped[dict | None] = mapped_column(JSONB)
    feedback: Mapped[bool | None] = mapped_column(Boolean)  # FALSE = 👎 (store in low_confidence_queries)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    whatsapp_message_id: Mapped[str | None] = mapped_column(Text)
    whatsapp_timestamp: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    message_type: Mapped[str] = mapped_column(Text, server_default="text", nullable=False)
    raw_payload: Mapped[dict | None] = mapped_column(JSONB)
    session_id: Mapped[int | None] = mapped_column(Integer)

    student: Mapped["Student"] = relationship(back_populates="messages", overlaps="messages,messages")
    college: Mapped["College"] = relationship(back_populates="messages", overlaps="messages,messages,student")
    session: Mapped["StudentSession"] = relationship(back_populates="messages", overlaps="college,messages,messages,student")


    __table_args__ = (
        CheckConstraint("messager_role IN ('student', 'assistant')", name="messages_messager_role_check"), 
        CheckConstraint("feedback IS NULL OR messager_role = 'assistant'", name="messages_feedback_assistant_check"),
        Index("ix_messages_student_id_created_at", "student_id", "created_at"), 
        Index("ix_messages_college_id_created_at", "college_id", "created_at"),
        Index("ix_messages_college_id_session_id", "college_id", "session_id"), 
        UniqueConstraint("college_id", "whatsapp_message_id"),
        UniqueConstraint("college_id", "message_id"),
        ForeignKeyConstraint(["college_id", "session_id"], ["student_sessions.college_id", "student_sessions.session_id"]),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
    )



class Document(Base):
    __tablename__ = "documents"

    document_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    extraction_method: Mapped[str | None] = mapped_column(Text)
    quality_score: Mapped[float | None] = mapped_column(Numeric(4, 3))
    num_pages: Mapped[int | None] = mapped_column(Integer)
    document_status: Mapped[str] = mapped_column(Text, nullable=False, server_default="processing")
    error: Mapped[str | None] = mapped_column(Text)
    uploaded_by: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="documents")
    uploaded_by_membership: Mapped["StaffCollege"] = relationship("StaffCollege", primaryjoin=("and_(Document.college_id == StaffCollege.college_id, " "Document.uploaded_by == StaffCollege.staff_id)"), foreign_keys="[Document.college_id, Document.uploaded_by]", viewonly=True)

    __table_args__ = (
        CheckConstraint("document_status IN ('processing', 'success', 'failed')", name="documents_document_status_check"),
        ForeignKeyConstraint(["college_id", "uploaded_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"]),
        UniqueConstraint("college_id", "document_id"),
        Index("ix_documents_college_id", "college_id")
    )



class LowConfidenceQuery(Base):
    __tablename__ = "low_confidence_queries"

    query_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    college_id: Mapped[int] = mapped_column(Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Numeric(5, 4))
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    resolved_by: Mapped[int | None] = mapped_column(Integer)
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    flagged_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    college: Mapped["College"] = relationship(back_populates="low_confidence_queries", overlaps="low_confidence_queries")
    student: Mapped["Student"] = relationship(back_populates="low_confidence_queries", overlaps="college,low_confidence_queries")
    question_message: Mapped["Message"] = relationship("Message", primaryjoin=("and_(LowConfidenceQuery.college_id == Message.college_id, " "LowConfidenceQuery.question_message_id == Message.message_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.question_message_id]", viewonly=True)
    answer_message: Mapped["Message"] = relationship("Message", primaryjoin=("and_(LowConfidenceQuery.college_id == Message.college_id, " "LowConfidenceQuery.answer_message_id == Message.message_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.answer_message_id]", viewonly=True)
    resolved_by_membership: Mapped["StaffCollege | None"] = relationship("StaffCollege", primaryjoin=("and_(LowConfidenceQuery.college_id == StaffCollege.college_id, " "LowConfidenceQuery.resolved_by == StaffCollege.staff_id)"), foreign_keys="[LowConfidenceQuery.college_id, LowConfidenceQuery.resolved_by]", viewonly=True,)
    
    __table_args__ = (
        UniqueConstraint("college_id", "query_id"),
        UniqueConstraint("college_id", "answer_message_id"),
        ForeignKeyConstraint(["college_id", "student_id"], ["students.college_id", "students.student_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "question_message_id"], ["messages.college_id", "messages.message_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "answer_message_id"], ["messages.college_id", "messages.message_id"], ondelete="CASCADE"),
        ForeignKeyConstraint(["college_id", "resolved_by"], ["staff_colleges.college_id", "staff_colleges.staff_id"],),
        Index("ix_low_confidence_queries_college_id_resolved", "college_id", "resolved"),
        Index("ix_low_confidence_queries_student_id", "student_id"),
    )



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