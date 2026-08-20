from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict



class StaffBase(BaseModel):
    staff_name: str = Field(min_length=2, max_length=100)
    staff_email: EmailStr = Field(max_length=150)


class StaffCreate(StaffBase):
    password: str = Field(min_length=8, max_length=100)
    is_active: bool = Field(default=True)


class StaffLogin(BaseModel):
    staff_email: EmailStr
    password: str = Field(min_length=8, max_length=100)


class StaffUpdate(BaseModel):
    staff_name: str | None = Field(default=None, min_length=2, max_length=100)
    staff_email: EmailStr | None = Field(default=None, max_length=150)
    is_active: bool | None = Field(default=None)
    password: str | None = Field(default=None, min_length=8, max_length=100)


class StaffResponse(StaffBase):
    model_config = ConfigDict(from_attributes=True)

    staff_id: int
    is_active: bool
    created_at: datetime


class StaffPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    staff_id: int
    is_active: bool
    staff_name: str = Field(min_length=2, max_length=100)


class Token(BaseModel):
    access_token: str
    token_type: str