from datetime import datetime
from pgvector.sqlalchemy import HALFVEC
from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class College(Base):
    __tablename__ = "colleges"

    college_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    college_name: Mapped[str] = mapped_column(Text, nullable=False)
    domain_name: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    # relationships
    students: Mapped[list["Student"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    staff: Mapped[list["CollegeStaff"]] = relationship(
        secondary="staff_colleges", back_populates="colleges"
    )
    whatsapp_numbers: Mapped[list["WhatsAppNumber"]] = relationship(
        back_populates="college", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="college", cascade="all, delete-orphan")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(
        back_populates="college", cascade="all, delete-orphan"
    )


class CollegeStaff(Base):
    __tablename__ = "college_staff"

    staff_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)

    colleges: Mapped[list["College"]] = relationship(
        secondary="staff_colleges", back_populates="staff"
    )


class StaffCollege(Base):
    __tablename__ = "staff_colleges"

    staff_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("college_staff.staff_id", ondelete="CASCADE"), primary_key=True
    )
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), primary_key=True
    )
    # Consider adding a `role` column here later (e.g. 'owner' vs 'viewer')
    # if you want different permission levels per staff-college pairing.
    # Skipping for now — not needed until you actually have colleges asking for it.

    __table_args__ = (
        Index("ix_staff_colleges_college_id", "college_id"),  # reverse lookup: which staff can access this college
    )


class Student(Base):
    __tablename__ = "students"

    student_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False
    )
    phone: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text)
    course_interest: Mapped[str | None] = mapped_column(Text)
    location: Mapped[str | None] = mapped_column(Text)
    academic_scores: Mapped[dict | None] = mapped_column(JSONB)  # e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary: Mapped[str | None] = mapped_column(Text)
    intent_tag: Mapped[str | None] = mapped_column(Text)  # e.g. 'high_intent', 'browsing', 'price_sensitive'
    status: Mapped[str] = mapped_column(Text, server_default="new")
    assigned_to: Mapped[str | None] = mapped_column(Text)  # staff name/email; plain text until real staff table exists
    internal_notes: Mapped[str | None] = mapped_column(Text)  # manual staff notes, separate from AI-generated summary
    message_count: Mapped[int] = mapped_column(Integer, server_default="0")
    last_message_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())  # last time STUDENT messaged
    last_contacted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)  # last time STAFF followed up (manual)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)

    __table_args__ = (
        UniqueConstraint("college_id", "phone"),
        CheckConstraint(
            "status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested')",
            name="students_status_check",
        ),
        Index("ix_students_college_id", "college_id"),
        Index("ix_students_college_id_status", "college_id", "status"),
    )

    college: Mapped["College"] = relationship(back_populates="students")
    messages: Mapped[list["Message"]] = relationship(back_populates="student", cascade="all, delete-orphan")
    low_confidence_queries: Mapped[list["LowConfidenceQuery"]] = relationship(
        back_populates="student", cascade="all, delete-orphan"
    )


class WhatsAppNumber(Base):
    __tablename__ = "whatsapp_numbers"

    number_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False
    )
    phone_number_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)  # Meta's ID, present in every webhook payload
    display_number: Mapped[str | None] = mapped_column(Text)  # human-readable, e.g. +91XXXXXXXXXX
    verified_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (Index("ix_whatsapp_numbers_college_id", "college_id"),)

    college: Mapped["College"] = relationship(back_populates="whatsapp_numbers")


class Message(Base):
    __tablename__ = "messages"

    message_id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(Text, nullable=False)  # 'student' | 'assistant'
    content: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[bool | None] = mapped_column(Boolean)  # NULL = no feedback, TRUE = 👍, FALSE = 👎
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        CheckConstraint("role IN ('student', 'assistant')", name="messages_role_check"),
        Index("ix_messages_student_id_created_at", "student_id", "created_at"),
    )

    student: Mapped["Student"] = relationship(back_populates="messages")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(HALFVEC(3072))
    source_type: Mapped[str] = mapped_column(Text, nullable=False)  # 'pdf' | 'web'
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    upload_session_id: Mapped[str] = mapped_column(Text, nullable=False)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        CheckConstraint("source_type IN ('pdf', 'web')", name="documents_source_type_check"),
        Index("ix_documents_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "halfvec_cosine_ops"}),
        Index("ix_documents_college_id_source_type", "college_id", "source_type"),
        Index("ix_documents_upload_session_id", "upload_session_id"),
    )

    college: Mapped["College"] = relationship(back_populates="documents")


class LowConfidenceQuery(Base):
    __tablename__ = "low_confidence_queries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, nullable=False)
    college_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("colleges.college_id", ondelete="CASCADE"), nullable=False
    )
    student_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("students.student_id", ondelete="CASCADE"), nullable=False
    )
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    similarity_score: Mapped[float] = mapped_column(Numeric(5, 4), nullable=False)
    resolved: Mapped[bool] = mapped_column(Boolean, server_default="false")
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    asked_at: Mapped[datetime] = mapped_column(TIMESTAMP, server_default=func.now())

    __table_args__ = (
        Index("ix_low_confidence_queries_college_id_resolved", "college_id", "resolved"),
        Index("ix_low_confidence_queries_student_id", "student_id"),
    )

    college: Mapped["College"] = relationship(back_populates="low_confidence_queries")
    student: Mapped["Student"] = relationship(back_populates="low_confidence_queries")