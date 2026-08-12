from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional


class CollegeBase(BaseModel):
    college_name: str = Field(min_length=2, max_length=100)
    college_phone: str = Field(min_length=10, max_length=15)
    college_email: EmailStr = Field(max_length=150)
    college_strengths: Optional[dict] = None


class CollegeCreate(CollegeBase):
    pass


class CollegeUpdate(BaseModel):
    college_name: str | None = Field(default=None, min_length=2, max_length=100)
    college_phone: str | None = Field(default=None, min_length=10, max_length=15)
    college_email: EmailStr | None = Field(default=None, max_length=150)
    college_strengths: dict | None = Field(default=None)


class CollegeResponse(CollegeBase):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    created_at: datetime