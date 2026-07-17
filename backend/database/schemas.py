from datetime import datetime
from pydantic import BaseModel, ConfigDict, EmailStr


class Student(BaseModel):
    model_config = ConfigDict(from_attributes=True) #  Teaches Pydantic how to read data from a database object (using dot notation, like student.name) instead of just a standard dictionary (like student['name']).
    student_id: int # What we use internally to identify a student in the database.
    # What whatsapp gives us
    college_id: int
    phone: str
    name: str | None = None
    # What the chatbot answers.
    course_interest: str | None = None
    location: str | None = None
    academic_scores: dict | None = None  # e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary: str | None = None
    intent_tag: str | None = None  # e.g. 'high_intent', 'browsing', 'price_sensitive'
    status: str = "new" # CHECK (status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested'))
    assigned_to: str | None = None # staff name currently following up if required gets handled on the frontend.
    internal_notes: str | None = None # What gets handled on the frontend.
    message_count: int = 0
    # Again whatsapp gives this to us
    last_message_at: datetime
    last_contacted_at: datetime | None = None
    created_at: datetime
    deleted_at: datetime | None = None # What gets handled on the frontend.

# Sent the instant a student's first WhatsApp message comes in — college_id is resolved server-side (via whatsapp_numbers -> phone_number_id), never trusted from client input.

class CreateStudent(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    college_id: int
    phone: str
    name: str | None = None

# Will be returned in the response from chatbot after summarizing the conversation with the student and it will actually update the student in the database.

class StudentSessionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    course_interest: str | None = None
    location: str | None = None
    academic_scores: dict | None = None # e.g. {"jee_main_percentile": 95.2, "class_12_percentage": 92}
    summary: str | None = None
    intent_tag: str | None = None  # e.g. 'high_intent', 'browsing', 'price_sensitive', 'not_interested'
    status: str = "new" # CHECK (status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested'))

# What gets handled on the frontend. This is what the college staff can update about a student.

class StudentStaffUpdate(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    assigned_to: str | None = None
    internal_notes: str | None = None
    status: str | None = None # CHECK (status IN ('new', 'contacted', 'interested', 'enrolled', 'not_interested'))
    last_contacted_at: datetime | None = None


class College(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    college_id: int
    college_name: str
    domain_name: str # website domain name, e.g. "example.edu"
    phone: str
    email: EmailStr
    created_at: datetime

class CollegeStaff(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    staff_id: int
    name: str
    email: EmailStr
    hashed_password: str

class StaffCollege(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    staff_id: int
    college_id: int
    # Consider adding a `role` column here later (e.g. 'owner' vs 'viewer')if you want different permission levels per staff-college pairing. Skipping for now — not needed until you actually have colleges asking for it.
 
class WhatsAppNumber(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    number_id: int
    college_id: int
    phone_number_id: str  # Meta's ID for this number, present in every webhook payload
    display_number: str | None = None  # human-readable, e.g. +91XXXXXXXXXX
    verified_at: datetime | None = None
    created_at: datetime

class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    message_id: int
    student_id: int
    role: str  # CHECK (role IN ('student', 'assistant'))
    content: str
    feedback: bool | None = None  # NULL = no feedback, TRUE = 👍, FALSE = 👎
    created_at: datetime

class Document(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    college_id: int
    content: str
    embedding: list[float] | None = None  # Assuming HALFVEC(3072) is a list of floats
    source_type: str  # CHECK (source_type IN ('pdf', 'web'))
    source_name: str
    upload_session_id: str
    chunk_index: int
    created_at: datetime

class LowConfidenceQuery(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    college_id: int
    student_id: int
    query_text: str
    similarity_score: float  # NUMERIC(5,4)
    resolved: bool = False
    resolved_at: datetime | None = None
    asked_at: datetime