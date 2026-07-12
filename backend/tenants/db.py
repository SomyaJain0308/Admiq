from datetime import datetime
from pydantic import BaseModel

class Colleges(BaseModel):
    college_id: str
    college_name: str | None = None
    college_phone: str | None = None
    college_email: str | None = None
    whatsapp_number: str | None = None
    created_at: datetime.now


def create_college(
        college_id,
        college_name,
        college_email,
        college_phone,
        whatsapp_number
        ):
    