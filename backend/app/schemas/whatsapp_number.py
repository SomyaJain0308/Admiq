from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class WhatsAppNumberCreate(BaseModel):
    # Meta's ID for this phone number within the WhatsApp Business Platform -
    # this is what shows up in every inbound webhook payload
    # (value.metadata.phone_number_id) and is how the app matches an
    # incoming message to a college, so it's what actually has to be
    # correct for anything to work.
    phone_number_id: str = Field(min_length=1, max_length=64)
    whatsapp_business_account_id: str = Field(min_length=1, max_length=64)
    # Human-readable form, e.g. "+91XXXXXXXXXX" - purely for display, not
    # used to match webhook payloads.
    display_number: str | None = Field(default=None, max_length=32)


class WhatsAppNumberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    number_id: int
    college_id: int
    phone_number_id: str
    whatsapp_business_account_id: str
    display_number: str | None
    verified_at: datetime | None
    created_at: datetime
