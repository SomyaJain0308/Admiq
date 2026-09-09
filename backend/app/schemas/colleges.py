from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional

from backend.app.schemas.staff import StaffCreate


class CollegeBase(BaseModel):
    college_name: str = Field(min_length=2, max_length=100)
    college_phone: str = Field(min_length=10, max_length=15)
    college_email: EmailStr = Field(max_length=150)
    college_strengths: Optional[list[str]] = None


class CollegeCreate(CollegeBase):
    # A brand-new college has no staff, so create_college takes the first
    # staff member's details in the same request and creates both rows in
    # one transaction - otherwise you'd need an already-logged-in staff
    # member to call create_staff afterwards, which nothing satisfies for
    # the very first college/staff pair in the system. Same StaffCreate
    # schema used by create_staff: password optional -> invite email flow.
    first_staff: StaffCreate


class CollegeUpdate(BaseModel):
    college_name: str | None = Field(default=None, min_length=2, max_length=100)
    college_phone: str | None = Field(default=None, min_length=10, max_length=15)
    college_email: EmailStr | None = Field(default=None, max_length=150)
    college_strengths: list[str] | None = Field(default=None)


class CollegeResponse(CollegeBase):
    model_config = ConfigDict(from_attributes=True)

    college_id: int
    created_at: datetime