from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class StudentMessageCreate(BaseModel):
    # WhatsApp text messages cap out at 4096 characters - reject oversized
    # content up front instead of letting the Cloud API bounce it.
    content: str = Field(min_length=1, max_length=4096)
    # Opt-in: when true, this direct message also gets run through the same
    # reconstruct-and-embed path the low-confidence queue's reply endpoint
    # uses, so it becomes a retrievable answer for future students asking
    # something similar - not just "say this to the student now."
    save_as_answer: bool = False
    # Only meaningful when save_as_answer is true. None = never expires,
    # matching the queue reply endpoint's existing behavior.
    expires_at: datetime | None = None


class StudentMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    message_id: int
    student_id: int
    content: str
    created_at: datetime
    delivered: bool
    # "text" = sent as a normal free-form WhatsApp message; "template" = the
    # 24h customer-service window had closed, so it went out via the
    # pre-approved template fallback instead (see whatsapp_service.
    # send_staff_initiated_message) and may read differently to the student
    # than the exact text staff typed.
    channel: str = "text"
    # Whether save_as_answer was actually honored. False either because it
    # wasn't requested, or because it was requested but couldn't be done
    # (see save_error) - the message send itself never fails on account of
    # this step, so the frontend needs to distinguish the two.
    saved_as_answer: bool = False
    reconstructed_question: str | None = None
    save_error: str | None = None


class StudentNotesUpdate(BaseModel):
    # None (or omitted -> None) clears the note - a staff member should be
    # able to remove one, not just add or overwrite it.
    internal_notes: str | None = Field(default=None, max_length=5000)


class StudentAssignUpdate(BaseModel):
    # None unassigns the student.
    assigned_to: int | None = None

