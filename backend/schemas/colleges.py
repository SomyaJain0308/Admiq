from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict

class College(BaseModel):
    college_id: int
    college_name: str
    college_phone: str
    college_email: str
    college_context: dict
    created_at: datetime


class CollegeBase(BaseModel):
    college_name: str = Field(min_lenght=2, max_length=100)
    college_phone: str = Field(min_length=10, max_length=15)
    college_email: EmailStr = Field(max_length=150)
    college_context: dict


class CollegeCreate(CollegeBase):
    ...


class CollegeUpdate(CollegeBase):
    college_name: str | None = Field(default=None, min_lenght=2, max_length=100)
    college_phone: str | None = Field(default=None, min_length=10, max_length=15)
    college_email: EmailStr | None = Field(default=None, max_length=150)
    college_context: dict | None


class CollegeDelete(CollegeBase):
    ...


class CollegeResponse(CollegeBase):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    created_at: datetime