from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class StudentMessageCreate(BaseModel):
    # WhatsApp text messages cap out at 4096 characters - reject oversized
    # content up front instead of letting the Cloud API bounce it.
    content: str = Field(min_length=1, max_length=4096)


class StudentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    student_id: int
    content: str
    created_at: datetime
    delivered: bool


class StudentNotesUpdate(BaseModel):
    # None (or omitted -> None) clears the note - a staff member should be
    # able to remove one, not just add or overwrite it.
    internal_notes: str | None = Field(default=None, max_length=5000)


class StudentAssignUpdate(BaseModel):
    # None unassigns the student.
    assigned_to: int | None = None

