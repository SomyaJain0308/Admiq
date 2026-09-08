from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


class CollegeBase(BaseModel):
    college_name: str = Field(min_length=2, max_length=100)
    college_phone: str = Field(min_length=10, max_length=15)
    college_email: EmailStr = Field(max_length=150)
    college_strengths: Optional[list[str]] = None


class CollegeCreate(CollegeBase):
    # widget_public_key is intentionally NOT accepted here - it's always
    # server-generated in create_college so it can never be client-supplied
    # or guessed. widget_allowed_origin can be set at creation time, or left
    # null and set later via PATCH once the college's site URL is confirmed.
    widget_allowed_origin: str | None = Field(default=None, max_length=255)


class CollegeUpdate(BaseModel):
    college_name: str | None = Field(default=None, min_length=2, max_length=100)
    college_phone: str | None = Field(default=None, min_length=10, max_length=15)
    college_email: EmailStr | None = Field(default=None, max_length=150)
    college_strengths: list[str] | None = Field(default=None)
    widget_allowed_origin: str | None = Field(default=None, max_length=255)


class CollegeResponse(CollegeBase):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    created_at: datetime
    widget_public_key: str | None = None
    widget_allowed_origin: str | None = None