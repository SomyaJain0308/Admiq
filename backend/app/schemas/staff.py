from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict



class StaffBase(BaseModel):
    staff_name: str = Field(min_length=2, max_length=100)
    staff_email: EmailStr = Field(max_length=150)


class StaffCreate(StaffBase):
    # Optional now: if left blank, the staff member is created with a random,
    # never-revealed placeholder password and sent an invite email to set
    # their own - see send_invite in the create_staff endpoint. Still
    # settable directly for cases where an admin wants to hand someone
    # credentials in person instead of relying on email.
    password: str | None = Field(default=None, min_length=8, max_length=100)
    is_active: bool = Field(default=True)


class StaffLogin(BaseModel):
    staff_email: EmailStr
    password: str = Field(min_length=8, max_length=100)


class StaffUpdate(BaseModel):
    staff_name: str | None = Field(default=None, min_length=2, max_length=100)
    staff_email: EmailStr | None = Field(default=None, max_length=150)
    is_active: bool | None = Field(default=None)
    password: str | None = Field(default=None, min_length=8, max_length=100)


class CollegeSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    college_id: int
    college_name: str


class StaffResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    staff_id: int
    staff_name: str
    staff_email: EmailStr
    is_active: bool
    created_at: datetime


class CurrentStaffResponse(StaffResponse):
    colleges: list[CollegeSummary]

class Token(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class ForgotPasswordRequest(BaseModel):
    staff_email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str = Field(min_length=8, max_length=100)